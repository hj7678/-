"""
调度引擎 —— 仿真引擎 + 模因求解器

支持双模式：
  col_count=1: 7 仓单列模式（D7/D9），无跨列移动，无公司连续性约束
  col_count=2: 14 仓双列模式（D8），完整跨列移动 + 公司连续性约束
"""
import random
import copy
from typing import Dict, List, Tuple, Optional

from scheduling.config import (
    VC, D, VB, E, MAX_CAP, CAR_START_WH,
    BASE_DIST_CONSTANT, LONG_DIST_CONSTANT,
    SAFE_DURATION_THRESHOLD, URGENCY_PENALTY_FACTOR,
    STOCK_REFILL_BELOW, STOCK_REFILL_LINE_ORDER, STOCK_TRIGGER_BELOW,
    STOCK_REFILL_BELOW_BOOST, STOCK_TRIGGER_BELOW_BOOST,
    STOCK_CRITICAL,
    COMPANY_STARVATION_PENALTY, LINE_STOP_PENALTY, PENALTY_BASE,
)
from scheduling.sched_types import BinState, StepDetail, ScheduleResult
from scheduling.bin_config import LINE_NAMES_D8, COMPANY_LINES_D8


class SchedulingEngine:

    def __init__(self, col_count: int, belt_id: str = ""):
        if col_count not in (1, 2):
            raise ValueError(f"col_count 必须为 1 或 2，实际: {col_count}")
        self.col_count = col_count
        self.belt_id = belt_id

    # ========================================================================
    # 坐标转换
    # ========================================================================

    def _get_pos(self, wh_id: int) -> int:
        """内部仓号 → 列内位置 (1-7)"""
        if self.col_count == 1:
            return wh_id
        mod = wh_id % 7
        return mod if mod != 0 else 7

    def _get_col(self, wh_id: int) -> int:
        """内部仓号 → 列号 (1 或 2)，单列模式始终返回 1"""
        if self.col_count == 1:
            return 1
        return 1 if 1 <= wh_id <= 7 else 2

    def _is_same_col_inc(self, prev_id: Optional[int], curr_id: int) -> bool:
        if prev_id is None:
            return False
        if self.col_count == 1:
            return curr_id >= prev_id
        col_prev = self._get_col(prev_id)
        col_curr = self._get_col(curr_id)
        return col_prev == col_curr and curr_id >= prev_id

    def _is_same_col_dec(self, prev_id: Optional[int], curr_id: int) -> bool:
        if prev_id is None:
            return False
        if self.col_count == 1:
            return curr_id < prev_id
        col_prev = self._get_col(prev_id)
        col_curr = self._get_col(curr_id)
        return col_prev == col_curr and curr_id < prev_id

    def _get_line_number(self, wh_id: int) -> int:
        """内部仓号 → 产线号 (1-7)"""
        if self.col_count == 1:
            return wh_id
        mod = wh_id % 7
        return mod if mod != 0 else 7

    # ========================================================================
    # 仿真引擎
    # ========================================================================

    def simulate_sequence(
        self,
        sequence: List[int],
        wh_data: Dict[int, dict],
        sum_tf: float = 0.0,
        pos: int = None,
        prev_wh: int = None,
    ) -> dict:
        """
        仿真一个上料序列，返回时序详情。
        wh_data: {wh_id: {'C': stock, 'c': rate, 'maintenance': bool}}
        """
        rows = []
        current_sum_tf = sum_tf
        current_pos = self._get_pos(CAR_START_WH) if pos is None else pos
        prev_id = prev_wh

        total_real_time = 0.0
        total_stop = 0.0
        total_tf = 0.0
        min_stock_level = float('inf')
        is_feasible = True

        company_stop_times = {}
        wh_stop_times = {}
        if self.col_count == 2:
            company_stop_times = {c: 0.0 for c in COMPANY_LINES_D8}

        for step, wh_id in enumerate(sequence, 1):
            info = wh_data[wh_id]
            C, c = info['C'], info['c']
            curr_pos = self._get_pos(wh_id)

            steps = abs(curr_pos - current_pos)
            tmi = steps * D / VC

            if self._is_same_col_inc(prev_id, wh_id):
                twi = (wh_id - prev_id) * D / VB
                mode_desc = "同列递增"
            elif self._is_same_col_dec(prev_id, wh_id):
                twi = (BASE_DIST_CONSTANT.get(self.belt_id, 17.4) + curr_pos * D) / VB
                mode_desc = "反向"
            else:
                twi = (LONG_DIST_CONSTANT + curr_pos * D) / VB
                mode_desc = "跨列"

            total_wait = current_sum_tf + tmi + twi
            remain = C - total_wait * c

            if remain < min_stock_level:
                min_stock_level = remain
            has_stock = remain > 1e-4
            tsi = 0.0

            if has_stock:
                tfi = (MAX_CAP - remain) / (E - c)
                stock_status = "维持生产"
            else:
                tfi = MAX_CAP / (E - c)
                time_capacity = C / c
                tsi = max(0.0, total_wait - time_capacity)
                is_feasible = False
                stock_status = "断料"

                line = self._get_line_number(wh_id)
                if wh_id not in wh_stop_times:
                    wh_stop_times[wh_id] = 0.0
                wh_stop_times[wh_id] += tsi
                if self.col_count == 2:
                    company = self._get_company(wh_id)
                    if company in company_stop_times:
                        company_stop_times[company] += tsi

            real_time_step = tmi + twi + tfi
            current_sum_tf += tfi + tmi + twi
            current_pos = curr_pos

            total_real_time += real_time_step
            total_stop += tsi
            total_tf += tfi

            rows.append({
                'step': step, 'wh_id': wh_id, 'pos': curr_pos,
                'prev_wh': prev_id if step > 1 else (prev_wh if prev_wh else '-'),
                'mode': mode_desc, 'move_steps': steps,
                'tmi': tmi, 'twi': twi, 'tfi': tfi, 'tsi': tsi,
                'total_step_time': real_time_step, 'remain_stock': remain,
                'stock_status': stock_status,
            })
            prev_id = wh_id

        result = {
            'total_time': total_real_time,
            'total_stop': total_stop,
            'min_stock': min_stock_level,
            'is_feasible': is_feasible,
            'total_tf': total_tf,
            'final_sum_tf': current_sum_tf,
            'final_pos': current_pos,
            'final_prev_wh': prev_id,
            'log': rows,
            'wh_stop_times': wh_stop_times,
        }
        if self.col_count == 2:
            result['company_stop_times'] = company_stop_times
        return result

    # ========================================================================
    # 求解器：模因算法
    # ========================================================================

    def _urgency_penalty(self, stock: float, rate: float) -> float:
        if rate <= 1e-9:
            return 0.0
        survival_time = stock / rate
        if survival_time >= SAFE_DURATION_THRESHOLD:
            return 0.0
        return URGENCY_PENALTY_FACTOR * (
            (1.0 / (survival_time + 1e-9)) - (1.0 / SAFE_DURATION_THRESHOLD)
        )

    def _get_company(self, wh_id: int) -> str:
        line = self._get_line_number(wh_id)
        for company, lines in COMPANY_LINES_D8.items():
            if line in lines:
                return company
        return 'UNKNOWN'

    def _is_gravel_wh(self, wh_id: int) -> bool:
        """14仓模式：仓 8-14 为碎石仓"""
        return wh_id > 7

    def _get_gravel_wh(self, line: int) -> int:
        return line + 7

    def _is_line_all_maintenance(self, line: int, wh_data: dict) -> bool:
        gravel_wh = self._get_gravel_wh(line)
        return wh_data.get(gravel_wh, {}).get('maintenance', False)

    def _is_line_stopped(self, line: int, wh_stop_times: dict, sequence: list, wh_data: dict) -> bool:
        gravel_wh = self._get_gravel_wh(line)
        if wh_data.get(gravel_wh, {}).get('maintenance', False):
            return False
        if gravel_wh not in sequence:
            return False
        return wh_stop_times.get(gravel_wh, 0.0) > 1e-6

    def _calc_company_penalty(self, res: dict, wh_data: dict, sequence: list) -> float:
        if self.col_count == 1:
            return 0.0

        cst = res.get('company_stop_times', {})
        wst = res.get('wh_stop_times', {})
        total = 0.0

        for company, lines in COMPANY_LINES_D8.items():
            active_lines = [ln for ln in lines if not self._is_line_all_maintenance(ln, wh_data)]
            if not active_lines:
                total += COMPANY_STARVATION_PENALTY
                continue
            all_stop = all(self._is_line_stopped(ln, wst, sequence, wh_data) for ln in active_lines)
            if all_stop:
                total += COMPANY_STARVATION_PENALTY

        for wh_id, stop_t in wst.items():
            total += LINE_STOP_PENALTY * stop_t

        return total

    def evaluate(self, seq: List[int], current_state: dict, wh_data: dict) -> Tuple[float, bool, float, float, dict]:
        res = self.simulate_sequence(seq, wh_data, **current_state)

        total_time = res['total_time']
        total_stop = res['total_stop']
        total_tf = res['total_tf']
        is_feasible = res['is_feasible']

        urgency = 0.0
        for entry in res['log']:
            wh_id = entry['wh_id']
            stock = entry['remain_stock']
            rate = wh_data[wh_id]['c']
            urgency += self._urgency_penalty(stock, rate)

        company_penalty = self._calc_company_penalty(res, wh_data, seq)

        if is_feasible:
            eps = 1e-9
            if total_time <= eps:
                score = PENALTY_BASE + urgency + company_penalty
            else:
                score = 10 * (total_time - total_tf) + urgency + company_penalty
            return score, True, total_time, 0.0, res
        else:
            score = PENALTY_BASE + 1000 * total_stop + company_penalty
            return score, False, total_time, total_stop, res

    def _greedy_heuristic(self, tasks: List[int], wh_data: dict) -> List[int]:
        urgency = [(wh_id, wh_data[wh_id]['C'] / wh_data[wh_id]['c']) for wh_id in tasks]
        urgency.sort(key=lambda x: x[1])
        return [x[0] for x in urgency]

    def _local_search(self, seq: List[int], current_state: dict, wh_data: dict, max_iter: int = 50) -> List[int]:
        best_seq = seq[:]
        best_score, _, _, _, _ = self.evaluate(best_seq, current_state, wh_data)

        improved = True
        iterations = 0
        while improved and iterations < max_iter:
            improved = False
            iterations += 1
            for i in range(len(best_seq) - 1):
                for j in range(i + 2, len(best_seq)):
                    candidate = best_seq[:i+1] + best_seq[i+1:j+1][::-1] + best_seq[j+1:]
                    score, _, _, _, _ = self.evaluate(candidate, current_state, wh_data)
                    if score < best_score - 1e-6:
                        best_score = score
                        best_seq = candidate
                        improved = True
                        break
                if improved:
                    break

        for i in range(len(best_seq)):
            for j in range(len(best_seq)):
                if i != j:
                    candidate = best_seq[:]
                    elem = candidate.pop(i)
                    candidate.insert(j, elem)
                    score, _, _, _, _ = self.evaluate(candidate, current_state, wh_data)
                    if score < best_score - 1e-6:
                        best_score = score
                        best_seq = candidate

        return best_seq

    def optimize(
        self,
        tasks: List[int],
        current_state: dict,
        wh_data: dict,
        original_seq: List[int] = None,
        pop_size: int = 80,
        generations: int = 100,
        restart_on_stagnation: bool = True,
        max_no_improve_rounds: int = 3,
    ) -> Tuple[List[int], dict]:
        if original_seq is None:
            original_seq = tasks[:]
        if len(tasks) <= 1:
            return list(tasks), {"reason": "SINGLE_TASK", "gain": 0}

        all_time_best_seq = None
        all_time_best_score = float('inf')
        all_time_best_feasible = None
        all_time_best_time = None
        all_time_best_stop = None
        no_improve_rounds = 0

        base_mutation_rate = 0.25
        elite_count = 5

        for round_idx in range(max_no_improve_rounds + 1):
            base_seed = 42 + round_idx * 1000
            random.seed(base_seed)

            population = []
            population.append(original_seq[:])
            greedy_seq = self._greedy_heuristic(tasks, wh_data)
            population.append(greedy_seq[:])
            population.append(greedy_seq[::-1])

            for i in range(len(greedy_seq) - 1):
                candidate = greedy_seq[:]
                candidate[i], candidate[i+1] = candidate[i+1], candidate[i]
                population.append(candidate)

            for _ in range(5):
                candidate = greedy_seq[:]
                i, j = random.sample(range(len(candidate)), 2)
                candidate[i], candidate[j] = candidate[j], candidate[i]
                population.append(candidate)

            while len(population) < pop_size:
                p = tasks[:]
                random.shuffle(p)
                population.append(p)

            scores = [self.evaluate(p, current_state, wh_data)[0] for p in population]
            sorted_idx = sorted(range(len(scores)), key=lambda i: scores[i])

            for i in range(min(8, len(population))):
                idx = sorted_idx[i]
                population[idx] = self._local_search(population[idx], current_state, wh_data)

            scores = [self.evaluate(p, current_state, wh_data)[0] for p in population]
            round_best_seq = population[min(range(len(scores)), key=lambda i: scores[i])][:]
            round_best_score, round_best_feasible, round_best_time, round_best_stop, _ = self.evaluate(
                round_best_seq, current_state, wh_data
            )

            stagnation_counter = 0
            current_mutation_rate = base_mutation_rate

            for gen in range(generations):
                next_gen = []
                elite_indices = sorted(range(len(scores)), key=lambda i: scores[i])[:elite_count]
                for idx in elite_indices:
                    elite = population[idx][:]
                    elite = self._local_search(elite, current_state, wh_data, max_iter=15)
                    next_gen.append(elite)

                while len(next_gen) < pop_size:
                    def tournament_select():
                        contestants = random.sample(range(len(population)), 4)
                        return min(contestants, key=lambda i: scores[i])

                    p1_idx = tournament_select()
                    p2_idx = tournament_select()
                    p1 = population[p1_idx][:]
                    p2 = population[p2_idx][:]
                    child = p1[:]

                    if random.random() < 0.85 and len(tasks) > 2:
                        start, end = sorted(random.sample(range(len(tasks)), 2))
                        child = [-1] * len(tasks)
                        child[start:end+1] = p1[start:end+1]
                        ptr = 0
                        for gene in p2:
                            if gene not in child:
                                while ptr < len(tasks) and child[ptr] != -1:
                                    ptr += 1
                                if ptr < len(tasks):
                                    child[ptr] = gene

                    if random.random() < current_mutation_rate:
                        i, j = random.sample(range(len(child)), 2)
                        child[i], child[j] = child[j], child[i]
                        if random.random() < 0.3:
                            start, end = sorted(random.sample(range(len(child)), 2))
                            child[start:end+1] = child[start:end+1][::-1]

                    if len(child) != len(tasks) or len(set(child)) != len(child) or any(x not in tasks for x in child):
                        missing = [gene for gene in tasks if gene not in child]
                        repaired = []
                        seen = set()
                        for x in child:
                            if x in tasks and x not in seen:
                                repaired.append(x)
                                seen.add(x)
                            elif missing:
                                repaired.append(missing.pop(0))
                        for g in tasks:
                            if g not in seen:
                                repaired.append(g)
                        child = repaired

                    next_gen.append(child)

                population = next_gen
                scores = [self.evaluate(p, current_state, wh_data)[0] for p in population]

                min_idx = min(range(len(scores)), key=lambda i: scores[i])
                curr_score = scores[min_idx]

                if curr_score < round_best_score - 1e-6:
                    round_best_score = curr_score
                    round_best_seq = population[min_idx][:]
                    _, round_best_feasible, round_best_time, round_best_stop, _ = self.evaluate(
                        round_best_seq, current_state, wh_data
                    )
                    stagnation_counter = 0
                    current_mutation_rate = base_mutation_rate
                else:
                    stagnation_counter += 1

                if stagnation_counter > 5:
                    current_mutation_rate = min(0.8, current_mutation_rate * 1.2)
                elif stagnation_counter > 10:
                    worst_indices = sorted(range(len(scores)), key=lambda i: scores[i])[-int(pop_size/2):]
                    for idx in worst_indices:
                        p = tasks[:]
                        random.shuffle(p)
                        population[idx] = p
                    stagnation_counter = 0
                    current_mutation_rate = 0.5

            final_best = self._local_search(round_best_seq, current_state, wh_data, max_iter=80)
            final_score, final_feas, final_time, final_stop, _ = self.evaluate(final_best, current_state, wh_data)

            if final_score < round_best_score - 1e-6:
                round_best_seq = final_best
                round_best_score = final_score
                round_best_feasible = final_feas
                round_best_time = final_time
                round_best_stop = final_stop

            if round_best_score < all_time_best_score - 1e-6:
                all_time_best_score = round_best_score
                all_time_best_seq = round_best_seq[:]
                all_time_best_feasible = round_best_feasible
                all_time_best_time = round_best_time
                all_time_best_stop = round_best_stop
                no_improve_rounds = 0
            else:
                no_improve_rounds += 1

            if restart_on_stagnation and no_improve_rounds >= max_no_improve_rounds:
                break

        best_seq = all_time_best_seq
        best_score = all_time_best_score
        best_feasible = all_time_best_feasible
        best_time = all_time_best_time
        best_stop = all_time_best_stop

        orig_score, orig_feas, orig_time, orig_stop, _ = self.evaluate(original_seq, current_state, wh_data)

        if best_seq == original_seq:
            return original_seq, {"reason": "NO_CHANGE", "gain": 0}
        if orig_feas and best_feasible:
            diff = orig_time - best_time
            if diff > 0.5:
                return best_seq, {"reason": "FASTER", "gain": diff}
            return original_seq, {"reason": "NO_GAIN", "gain": 0}
        elif orig_feas and not best_feasible:
            return original_seq, {"reason": "AVOID_INFEASIBLE", "gain": 0}
        elif not orig_feas and best_feasible:
            return best_seq, {"reason": "BECAME_FEASIBLE", "gain": orig_stop}
        else:
            diff = orig_stop - best_stop
            if diff > 0.5:
                return best_seq, {"reason": "LESS_STOPPAGE", "gain": diff}
            return original_seq, {"reason": "NO_STOPPAGE_GAIN", "gain": 0}

    # ========================================================================
    # 公共接口
    # ========================================================================

    def check_trigger(self, bins: List[BinState], boost: bool = False) -> Tuple[bool, str]:
        trigger_below = STOCK_TRIGGER_BELOW_BOOST if boost else STOCK_TRIGGER_BELOW
        for b in bins:
            if b.maintenance:
                continue
            if b.stock < trigger_below:
                return True, f"仓{b.bin_id}库存{b.stock:.1f} < {trigger_below}"
        return False, ""

    def get_eligible_bins(self, bins: List[BinState], boost: bool = False) -> List[BinState]:
        refill_below = STOCK_REFILL_BELOW_BOOST if boost else STOCK_REFILL_BELOW
        eligible = []
        for b in bins:
            if b.maintenance:
                continue
            if b.stock < refill_below:
                eligible.append(b)
            elif b.stock < STOCK_REFILL_LINE_ORDER and b.has_future_order:
                eligible.append(b)
        return eligible

    def _bins_to_wh_data(self, bins: List[BinState], wh_ids: List[int], wh_to_bin) -> Dict[int, dict]:
        """将 BinState 列表转换为内部 wh_data 字典。wh_to_bin: wh_id → bin_id"""
        bin_map = {b.bin_id: b for b in bins}
        result = {}
        for wh_id in wh_ids:
            bin_id = wh_to_bin(wh_id)
            b = bin_map.get(bin_id)
            if b:
                result[wh_id] = {'C': b.stock, 'c': b.consumption_rate, 'maintenance': b.maintenance}
        return result

    def solve(self, bins: List[BinState], boost: bool = False,
              cart_position: int = None) -> ScheduleResult:
        """主入口：输入料仓状态，输出调度结果

        Args:
            cart_position: 小车当前位置（1-based），None 则使用默认值
        """
        from scheduling.bin_config import (
            bin_id_to_wh, d8_bin_id_to_wh, d8_wh_to_bin_id,
            make_wh_to_bin_id, BELT_TO_COL_PREFIX,
        )
        from scheduling.config import SILO_MAX_CAP, SILO_TRIGGER_PCT

        # D6 高位储料仓：简单规则（最低料位优先）
        if self.belt_id == 'D6':
            trigger_level = SILO_MAX_CAP * SILO_TRIGGER_PCT / 100.0
            lowest_bin = None
            lowest_stock = float('inf')
            for b in bins:
                if b.stock < trigger_level and b.stock < lowest_stock:
                    lowest_stock = b.stock
                    lowest_bin = b.bin_id
            if lowest_bin is None:
                return ScheduleResult(belt_id=self.belt_id, is_feasible=True)
            line_names = {
                'S1': '20mm碎石', 'S2': '20mm碎石', 'S3': '20mm碎石',
                'S4': '20mm碎石', 'S5': '20mm碎石', 'S6': '20mm碎石',
                'S7': '石粉', 'S8': '石粉',
                'S9': '10mm碎石', 'S10': '10mm碎石', 'S11': '10mm碎石', 'S12': '10mm碎石',
            }
            return ScheduleResult(
                belt_id=self.belt_id,
                sequence=[lowest_bin],
                steps=[StepDetail(
                    seq=1, bin_id=lowest_bin,
                    line_name=line_names.get(lowest_bin, lowest_bin),
                    mode='auto', remain_stock=round(lowest_stock, 2),
                    survival_time=0, stock_status='补料',
                    move_time=0, wait_time=0, fill_time=0,
                    stop_time=0, total_time=0,
                )],
                total_move=0, total_wait=0, total_fill=0, total_stop=0,
                is_feasible=True,
            )

        if self.col_count == 2:
            fwd_func = d8_bin_id_to_wh      # bin_id → wh_id
            rev_func = d8_wh_to_bin_id       # wh_id → bin_id
            all_wh_ids = list(range(1, 15))
        else:
            prefix = BELT_TO_COL_PREFIX.get(self.belt_id, 'P1')
            fwd_func = bin_id_to_wh
            rev_func = make_wh_to_bin_id(prefix)
            all_wh_ids = list(range(1, 8))

        wh_data = self._bins_to_wh_data(bins, all_wh_ids, rev_func)

        trigger, reason = self.check_trigger(bins, boost)
        if not trigger:
            return ScheduleResult(belt_id=self.belt_id, is_feasible=True)

        eligible = self.get_eligible_bins(bins, boost)
        if not eligible:
            return ScheduleResult(belt_id=self.belt_id, is_feasible=True)

        eligible_ids = [fwd_func(b.bin_id) for b in eligible]

        if self.col_count == 1:
            start_pos = cart_position if cart_position is not None else 1
            start_prev = start_pos
        else:
            start_pos = self._get_pos(cart_position) if cart_position is not None else self._get_pos(CAR_START_WH)
            start_prev = cart_position if cart_position is not None else CAR_START_WH

        current_state = {'sum_tf': 0.0, 'pos': start_pos, 'prev_wh': start_prev}

        # 关键料仓优先：料位 ≤ STOCK_CRITICAL 的料仓置顶
        critical_bins = [(b, fwd_func(b.bin_id)) for b in eligible
                         if b.stock <= STOCK_CRITICAL]
        if critical_bins:
            if self.col_count == 2:
                critical_bins.sort(key=lambda x: (x[1] <= 7, x[0].stock))
            else:
                critical_bins.sort(key=lambda x: x[0].stock)
            priority_prefix = [wh_id for _, wh_id in critical_bins]
            remaining_ids = [wid for wid in eligible_ids if wid not in priority_prefix]
            if remaining_ids:
                opt_ids, info = self.optimize(
                    remaining_ids, current_state, wh_data, remaining_ids)
                opt_ids = priority_prefix + opt_ids
            else:
                opt_ids = priority_prefix
                info = {}
        else:
            opt_ids, info = self.optimize(eligible_ids, current_state, wh_data, eligible_ids)

        # 按最优序列逐步仿真，收集 StepDetail
        current_state = {'sum_tf': 0.0, 'pos': start_pos, 'prev_wh': start_prev}
        steps = []
        accumulated_move = 0.0
        accumulated_wait = 0.0
        accumulated_fill = 0.0
        accumulated_stop = 0.0

        for step_idx, wh_id in enumerate(opt_ids, 1):
            res = self.simulate_sequence([wh_id], wh_data, **current_state)
            entry = res['log'][0]
            rate = wh_data[wh_id]['c']
            survival = entry['remain_stock'] / rate if rate > 1e-9 else float('inf')

            if self.col_count == 2:
                line_name = LINE_NAMES_D8.get(wh_id, str(wh_id))
            else:
                line_name = f"产线{wh_id}"

            stock_status = "断料" if survival < 0 else ("告急" if survival < SAFE_DURATION_THRESHOLD else "安全")

            steps.append(StepDetail(
                seq=step_idx,
                bin_id=rev_func(wh_id),
                line_name=line_name,
                mode=entry['mode'],
                remain_stock=round(entry['remain_stock'], 2),
                survival_time=round(survival, 1),
                stock_status=stock_status,
                move_time=round(entry['tmi'], 1),
                wait_time=round(entry['twi'], 1),
                fill_time=round(entry['tfi'], 1),
                stop_time=round(entry['tsi'], 1),
                total_time=round(entry['total_step_time'], 1),
            ))

            accumulated_move += entry['tmi']
            accumulated_wait += entry['twi']
            accumulated_fill += entry['tfi']
            accumulated_stop += entry['tsi']

            current_state['sum_tf'] = res['final_sum_tf']
            current_state['pos'] = res['final_pos']
            current_state['prev_wh'] = res['final_prev_wh']

        return ScheduleResult(
            belt_id=self.belt_id,
            sequence=[rev_func(wh) for wh in opt_ids],
            steps=steps,
            total_move=round(accumulated_move, 1),
            total_wait=round(accumulated_wait, 1),
            total_fill=round(accumulated_fill, 1),
            total_stop=round(accumulated_stop, 1),
            is_feasible=res['is_feasible'],
        )
