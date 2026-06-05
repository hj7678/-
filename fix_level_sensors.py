import json

path = r'c:\Users\HJ\PycharmProjects\zsysl\sensor_simulate\data\generate_data.json'
d = json.load(open(path, 'r'))
ls = d.get('level_sensors', {})
for k in ls:
    ls[k]['unit'] = '%'
    ls[k]['value'] = 85.0
d['level_sensors'] = ls
json.dump(d, open(path, 'w'), indent=4, ensure_ascii=False)
print("Fixed level sensors:")
for k, v in list(ls.items())[:5]:
    print(f"  {k}: value={v.get('value')}, unit={v.get('unit')}")
print(f"Total: {len(ls)}")