# Audite: automatic change auditing for SQLite

Audite uses SQL triggers to automatically log all INSERT, UPDATE, and DELETE
operations on a target SQLite database. It gives you a totally-ordered history
of all changes to your data without touching your application code or running
an extra process.

## Example

Let's create `shop.db`, a database with the following schema:

```sh
sqlite3 shop.db "CREATE TABLE IF NOT EXISTS products (name TEXT PRIMARY KEY, price REAL NOT NULL)"
```

### Step 1: Enable auditing via the audite CLI
You only need to do this once per database/schema:

```sh
python3 -m audite shop.db
```

### Step 2: Create, Update, and Delete some data
This example uses the `sqlite3` CLI to make changes, but any interface into
your SQLite database should work.

Add some products:
```sh
sqlite3 shop.db "INSERT INTO products (name, price) VALUES ('notebook', 2.99), ('pen', 0.25)"
```

Adjust for inflation:
```sh
sqlite3 shop.db "UPDATE products SET price = ROUND(price * 1.1, 2)"
```

Whoops, we sold out of pens:
```sh
sqlite3 shop.db "DELETE FROM products WHERE name = 'pen'"
```

### Step 3: Query the event history

```sh
sqlite3 shop.db "SELECT * FROM audite_history ORDER BY id"
```

You should get back something like:
```
id  source    subject   type              time        specversion  data
--  --------  --------  ----------------  ----------  -----------  -------------------------------------------------------------------------------
1   products  notebook  products.created  1669046846  1.0          {"new":{"price":2.99,"name":"notebook"}}
2   products  pen       products.created  1669046846  1.0          {"new":{"price":0.25,"name":"pen"}}
3   products  notebook  products.updated  1669046866  1.0          {"new":{"price":3.29,"name":"notebook"},"old":{"price":2.99,"name":"notebook"}}
4   products  pen       products.updated  1669046866  1.0          {"new":{"price":0.28,"name":"pen"},"old":{"price":0.25,"name":"pen"}}
5   products  pen       products.deleted  1669046885  1.0          {"old":{"price":0.28,"name":"pen"}}
```

#### Event Schema
- `id` uniquely identifies the event.
- `source` is name of the database table that changed.
- `subject` is the primary key of the database row that changed.
- `type` describes the type of change: `*.created`, `*.updated`, or `*.deleted`.
- `time` is the unix epoch timestamp when the change was committed.
- `specversion` is the verion of the [CloudEvents spec](https://github.com/cloudevents/spec) in use, currently `1.0`.
- `data` is a JSON snapshot of the row that changed. The `data.new` object holds the post-change values and is present for `*.created` and `*.updated` events. The `data.old` object holds pre-change values and is present for `*.updated` and `*.deleted` events.

The event schema follows the [CloudEvents
spec](https://github.com/cloudevents/spec) with two exceptions: `id` and `time`
are integers instead of strings so that SQLite can store and sort them
efficiently. To conform exactly to the [CloudEvents JSON
spec](https://github.com/cloudevents/spec/blob/main/cloudevents/formats/json-format.md#23-examples),
you can query the `audite_cloudevents` view instead of the underlying
`audite_history` table:

```sh
sqlite3 shop.db "SELECT id, cloudevent FROM audite_cloudevents ORDER BY id"
```

## Handling database schema changes
It's safe to run `python3 -m audite` multiple times, including as part of your
app's startup script. When your database schema hasn't changed, then re-running
audite is effectively a noop; when your schema _has_ changed, then re-running
audite will ensure that incoming changes are saved with the latest schema.
