# create_insert_sql_from_json_data

a simple python script Create Postgresql insert into SQL base on JSON data

## How to get started

```bash
pip install psycopg2-binary
python create.py
```

## Type map

First level data will map to insert into SQL use the same element name.

if the sub-element is object/array or other will dump to JSON string, you can use jsonb type to save in the table.

```python
    if obj is None:
        return 'NULL'
    elif obj is True:
        return "'t'"
    elif obj is False:
        return "'f'"
    elif isinstance(obj, int):
        return str(obj)
    elif datetime and isinstance(obj, datetime.datetime):
        return repr(obj.isoformat())
    elif isinstance(obj, str):
        return repr(obj.encode('utf8'))
    else:
        return repr(json.dumps(obj))

```

## multiple insert

If has multiple data need insert you can put in `[]`, then call `createMultipleInsertSQL` create multiple insert SQL.

**Must make sure all the element has same attr**

## Note

most codes come from [web.py](https://github.com/webpy/webpy) old version, I miss the days when I used [web.py](https://github.com/webpy/webpy)

I just split min relation code into this script and make it support python3.
