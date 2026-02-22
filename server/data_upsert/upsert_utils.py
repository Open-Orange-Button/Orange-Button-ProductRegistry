import duckdb
import polars as pl


def compute_insert(rows, target_table_name, pk, superclass=None):
    varchar_present = duckdb.sql(r"""
    select column_name from (describe rows)
    """)
    varchar_columns = duckdb.sql(f"""
    select column_name from (describe {target_table_name})
    where column_type = 'VARCHAR'
    """)
    varchar_needs_fill = duckdb.sql("""
    select * from varchar_columns
    except
    select * from varchar_present
    """)
    varchar_fill = None
    if len(varchar_needs_fill) > 0:
        varchar_fill = duckdb.sql("""
        pivot (
            select column_name, '' as value from varchar_needs_fill
        ) on column_name using first(value)
        """)
    if superclass is None:
        max_id = duckdb.sql(f"""
        select coalesce(max({pk}), 0) from {target_table_name}
        """).fetchone()[0]
        to_insert = duckdb.sql(f"""
        select
            row_number() over () + {max_id} as {pk},
            *,
        from rows {'cross join varchar_fill' if varchar_fill is not None else ''}
        """)
    else:
        to_insert = duckdb.sql(f"""
        select
            superclass.{pk},
            rows.*,
           {'varchar_fill.*,' if varchar_fill is not None else ''}
        from rows {'cross join varchar_fill' if varchar_fill is not None else ''}
        join superclass using (csv_row_id)
        """)
    return to_insert


def insert_recursive(rows, target_table_name, pk='id', fk_fills=None):
    if fk_fills is None:
        fk_fills = []
    superclass = None
    fk_inserts = []
    for fk_column_name, kwargs in fk_fills:
        if 'rows' not in kwargs:
            kwargs['rows'] = duckdb.sql("select csv_row_id from rows")
        is_superclass = kwargs.pop('superclass', None)
        fk_inserts.append(
            insert_recursive(**kwargs).pl()
            .sort('csv_row_id')
            .select(
                'csv_row_id',
                pl.col(kwargs['pk']).alias(fk_column_name),
            )
        )
        if is_superclass:
            if superclass is not None:
                raise ValueError(f'{target_table_name} has more than one superclass, but it should have only one.')
            superclass = fk_inserts.pop()
    to_insert = compute_insert(rows, target_table_name, pk, superclass=superclass)
    if len(fk_fills) > 0:
        fk_inserts = [df.drop('csv_row_id') for df in fk_inserts]
        fk_inserts.append(to_insert.pl().sort('csv_row_id'))
        to_insert = pl.concat(fk_inserts, how='horizontal')
    duckdb.sql(f"""
    insert into {target_table_name} by name
    select * exclude(csv_row_id) from to_insert
    """)
    return duckdb.sql(f"select csv_row_id, {pk} from to_insert")
