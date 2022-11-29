# Audite: instant Change Data Capture for SQLite

Audite uses SQL triggers to add a transactional change feed to any SQLite
database. It gives you a totally-ordered history of all changes to your data,
without touching your application code or running an extra process.

## Use cases
- Track what changed when
- Restore previous versions of changed rows
- Replicate data to external systems by streaming the change feed

## Quick start

Let's add a changefeed to `todo.db`, a SQLite database with the following schema:

```sh
sqlite3 todo.db "CREATE TABLE task (name TEXT PRIMARY KEY, done BOOLEAN NOT NULL DEFAULT FALSE)"
```

1. **Install audite on your sytem**
    ```sh
    python3 -m pip install audite
    ```
2. **Enable audite on your database**
    ```sh
    python3 -m audite todo.db
    ```

Done! Now any process can INSERT, UPDATE, and DELETE from your DB as usual, and
audite's triggers will log these operations as [change events](#event-schema)
in the `audite_history` table. All (and only) committed transactions will
appear in the history. You only need to apply audite once per database/schema.

## Modfying data and querying the change feed

We'll add two tasks...

```sh
sqlite3 todo.db "INSERT INTO task (name) VALUES ('try audite'), ('profit')"
```

cross one off the list...
```sh
sqlite3 todo.db "UPDATE task SET done = TRUE WHERE name = 'try audite'"
```

and cancel the other:
```sh
sqlite3 todo.db "DELETE FROM task WHERE name = 'profit'"
```

### Now let's see what changed:
```sh
sqlite3 todo.db "SELECT * FROM audite_history ORDER BY id"
```

You should get back something like this:
```
id  source  subject     type          time        specversion  data
--  ------  ----------  ------------  ----------  -----------  ---------------------------------------------------------------------------
1   task    try audite  task.created  1669687674  1.0          {"new":{"done":0,"name":"try audite"}}
2   task    profit      task.created  1669687674  1.0          {"new":{"done":0,"name":"profit"}}
3   task    try audite  task.updated  1669687683  1.0          {"new":{"done":1,"name":"try audite"},"old":{"done":0,"name":"try audite"}}
4   task    profit      task.deleted  1669687690  1.0          {"old":{"done":0,"name":"profit"}}
```

## Event Schema
The event schema follows the [CloudEvents
spec](https://github.com/cloudevents/spec) so that other systems can easily
handle events from yours.

- `id` uniquely identifies the event.
- `source` is name of the database table that changed.
- `subject` is the primary key of the database row that changed.
- `type` describes the type of change: `*.created`, `*.updated`, or `*.deleted`.
- `time` is the Unix time when the change was committed.
- `specversion` is the verion of the [CloudEvents spec](https://github.com/cloudevents/spec) in use, currently `1.0`.
- `data` is a JSON snapshot of the row that changed. The `data.new` object holds the post-change values and is present for `*.created` and `*.updated` events. The `data.old` object holds pre-change values and is present for `*.updated` and `*.deleted` events.

**Note:** Audite stores `id` and `time` as integers so that SQLite can store
and sort them efficiently, but the CloudEvents spec mandates strings. To query
events that conform exactly to the spec, select rows as JSON from the
`audite_cloudevents` view instead of the underlying `audite_history` table:

```sh
sqlite3 todo.db "SELECT cloudevent FROM audite_cloudevents ORDER BY id"

{"id":"1","sequence":"00000000000000000001","source":"task","subject":"try audite","type":"task.created","time":"2022-11-29T02:07:54+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"done":0,"name":"try audite"}}}
{"id":"2","sequence":"00000000000000000002","source":"task","subject":"profit","type":"task.created","time":"2022-11-29T02:07:54+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"done":0,"name":"profit"}}}
{"id":"3","sequence":"00000000000000000003","source":"task","subject":"try audite","type":"task.updated","time":"2022-11-29T02:08:03+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"done":1,"name":"try audite"},"old":{"done":0,"name":"try audite"}}}
{"id":"4","sequence":"00000000000000000004","source":"task","subject":"profit","type":"task.deleted","time":"2022-11-29T02:08:10+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"old":{"done":0,"name":"profit"}}}
```

## Handling database schema changes
It's safe to run `python3 -m audite` multiple times, including as part of your
app's startup script. When your database schema hasn't changed, then re-running
audite does nothing. And when your schema has changed, then re-running audite
ensures that incoming changes are tracked with the latest schema.
