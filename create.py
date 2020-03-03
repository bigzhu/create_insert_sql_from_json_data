import psycopg2
import json
import datetime


def sqlify(obj):
    """
    converts `obj` to its proper SQL version

        >>> sqlify(None)
        'NULL'
        >>> sqlify(True)
        "'t'"
        >>> sqlify(3)
        '3'
    """
    # because `1 == True and hash(1) == hash(True)`
    # we have to do this the hard way...

    if obj is None:
        return 'NULL'
    elif obj is True:
        return "'t'"
    elif obj is False:
        return "'f'"
    elif isinstance(obj, int):
        return str(obj)
    elif isinstance(obj, dict):
        return repr(json.dumps(obj))
    elif isinstance(obj, list):
        return repr(json.dumps(obj))
    elif datetime and isinstance(obj, datetime.datetime):
        return repr(obj.isoformat())
    else:
        if isinstance(obj, str):
            obj = obj.encode('utf8')
        return repr(obj)


def safestr(obj, encoding='utf-8'):
    r"""
    Converts any given object to utf-8 encoded string.

        >>> safestr('hello')
        'hello'
        >>> safestr(u'\u1234')
        '\xe1\x88\xb4'
        >>> safestr(2)
        '2'
    """
    if isinstance(obj, str):
        return obj
    elif hasattr(obj, 'next'):  # iterator
        return itertools.imap(safestr, obj)
    else:
        return str(obj)


class SQLLiteral:
    """
    Protects a string from `sqlquote`.

        >>> sqlquote('NOW()')
        <sql: "'NOW()'">
        >>> sqlquote(SQLLiteral('NOW()'))
        <sql: 'NOW()'>
    """

    def __init__(self, v):
        self.v = v

    def __repr__(self):
        return self.v


class UnknownParamstyle(Exception):
    """
    raised for unsupported db paramstyles

    (currently supported: qmark, numeric, format, pyformat)
    """
    pass


class SQLParam(object):
    """
    Parameter in SQLQuery.

        >>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam("joe")])
        >>> q
        <sql: "SELECT * FROM test WHERE name='joe'">
        >>> q.query()
        'SELECT * FROM test WHERE name=%s'
        >>> q.values()
        ['joe']
    """
    __slots__ = ["value"]

    def __init__(self, value):
        self.value = value

    def get_marker(self, paramstyle='pyformat'):
        if paramstyle == 'qmark':
            return '?'
        elif paramstyle == 'numeric':
            return ':1'
        elif paramstyle is None or paramstyle in ['format', 'pyformat']:
            return '%s'
        raise UnknownParamstyle()

    def sqlquery(self):
        return SQLQuery([self])

    def __add__(self, other):
        return self.sqlquery() + other

    def __radd__(self, other):
        return other + self.sqlquery()

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return '<param: %s>' % repr(self.value)


sqlparam = SQLParam


class SQLQuery(object):
    """
    You can pass this sort of thing as a clause in any db function.
    Otherwise, you can pass a dictionary to the keyword argument `vars`
    and the function will call reparam for you.

    Internally, consists of `items`, which is a list of strings and
    SQLParams, which get concatenated to produce the actual query.
    """
    __slots__ = ["items"]

    # tested in sqlquote's docstring
    def __init__(self, items=None):
        r"""Creates a new SQLQuery.

            >>> SQLQuery("x")
            <sql: 'x'>
            >>> q = SQLQuery(['SELECT * FROM ', 'test', ' WHERE x=', SQLParam(1)])
            >>> q
            <sql: 'SELECT * FROM test WHERE x=1'>
            >>> q.query(), q.values()
            ('SELECT * FROM test WHERE x=%s', [1])
            >>> SQLQuery(SQLParam(1))
            <sql: '1'>
        """
        if items is None:
            self.items = []
        elif isinstance(items, list):
            self.items = items
        elif isinstance(items, SQLParam):
            self.items = [items]
        elif isinstance(items, SQLQuery):
            self.items = list(items.items)
        else:
            self.items = [items]

        # Take care of SQLLiterals
        for i, item in enumerate(self.items):
            if isinstance(item, SQLParam) and isinstance(item.value, SQLLiteral):
                self.items[i] = item.value.v

    def append(self, value):
        self.items.append(value)

    def __add__(self, other):
        if isinstance(other, str):
            items = [other]
        elif isinstance(other, SQLQuery):
            items = other.items
        else:
            return NotImplemented
        return SQLQuery(self.items + items)

    def __radd__(self, other):
        if isinstance(other, str):
            items = [other]
        else:
            return NotImplemented

        return SQLQuery(items + self.items)

    def __iadd__(self, other):
        if isinstance(other, (str, SQLParam)):
            self.items.append(other)
        elif isinstance(other, SQLQuery):
            self.items.extend(other.items)
        else:
            return NotImplemented
        return self

    def __len__(self):
        return len(self.query())

    def query(self, paramstyle=None):
        """
        Returns the query part of the sql query.
            >>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam('joe')])
            >>> q.query()
            'SELECT * FROM test WHERE name=%s'
            >>> q.query(paramstyle='qmark')
            'SELECT * FROM test WHERE name=?'
        """
        s = []
        for x in self.items:
            if isinstance(x, SQLParam):
                x = x.get_marker(paramstyle)
                s.append(safestr(x))
            else:
                x = safestr(x)
                # automatically escape % characters in the query
                # For backward compatability, ignore escaping when the query looks already escaped
                if paramstyle in ['format', 'pyformat']:
                    if '%' in x and '%%' not in x:
                        x = x.replace('%', '%%')
                s.append(x)
        return "".join(s)

    def values(self):
        """
        Returns the values of the parameters used in the sql query.
            >>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam('joe')])
            >>> q.values()
            ['joe']
        """
        return [i.value for i in self.items if isinstance(i, SQLParam)]

    def join(items, sep=' ', prefix=None, suffix=None, target=None):
        """
        Joins multiple queries.

        >>> SQLQuery.join(['a', 'b'], ', ')
        <sql: 'a, b'>

        Optinally, prefix and suffix arguments can be provided.

        >>> SQLQuery.join(['a', 'b'], ', ', prefix='(', suffix=')')
        <sql: '(a, b)'>

        If target argument is provided, the items are appended to target instead of creating a new SQLQuery.
        """
        if target is None:
            target = SQLQuery()

        target_items = target.items

        if prefix:
            target_items.append(prefix)

        for i, item in enumerate(items):
            if i != 0:
                target_items.append(sep)
            if isinstance(item, SQLQuery):
                target_items.extend(item.items)
            else:
                target_items.append(item)

        if suffix:
            target_items.append(suffix)
        return target

    join = staticmethod(join)

    def _str(self):
        try:
            return self.query() % tuple([sqlify(x) for x in self.values()])
        except (ValueError, TypeError):
            return self.query()

    def __str__(self):
        return safestr(self._str())

    def __unicode__(self):
        return safeunicode(self._str())

    def __repr__(self):
        return '<sql: %s>' % repr(str(self))


def test():
    from jsonschema2db import JSONSchemaToPostgres
    schema = json.load(open('result.json'))
    translator = JSONSchemaToPostgres(
        schema,
        postgres_schema='kafka_test',
        # item_col_name='order_id',
        # item_col_type='string',
    )

    con = psycopg2.connect(
        'user=kafka_test host=127.0.0.1 dbname=kafka_test password=kafka_test')
    translator.create_tables(con)


def createInsertSQL(table_name, **values):
    def q(x): return "(" + x + ")"
    _keys = SQLQuery.join(values.keys(), ', ')
    _values = SQLQuery.join([sqlparam(v) for v in values.values()], ', ')
    sql_query = "INSERT INTO %s " % table_name + \
        q(_keys) + ' VALUES ' + q(_values)
    return sql_query


def createMultipleInsertSQL(table_name, values):
    keys = sorted(values[0].keys())
    # @@ make sure all keys are valid

    for v in values:
        # make sure keys are sorted, keep compare correct
        if sorted(v.keys()) != keys:
            raise ValueError('Not all rows have the same keys')

    sql_query = SQLQuery('INSERT INTO %s (%s) VALUES ' %
                         (table_name, ', '.join(keys)))

    for i, row in enumerate(values):
        if i != 0:
            sql_query.append(", ")
        SQLQuery.join([SQLParam(row[k]) for k in keys], sep=", ",
                      target=sql_query, prefix="(", suffix=")")
    return sql_query


if __name__ == "__main__":
    #o = json.load(open('20200105_182621258_0.json'))
    #print(createInsertSQL("good_table", **o))
    o = json.load(open('test.json'))
    print(createMultipleInsertSQL("good_table", o))
