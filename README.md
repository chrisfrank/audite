# Audite: instant change feeds for SQLite

Audite uses SQL triggers to add a transactional change feed to any SQLite
database. It gives you a totally-ordered audit history of all changes to your
data, without touching your application code or running an extra process.

## Use cases
- Track who changed what, when
- Restore previous versions of changed rows
- Replicate data to external systems by streaming the change feed

## Quick start

Let's add a changefeed to `todo.db`, a SQLite database with the following schema:

```sh
sqlite3 todo.db "CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT)"
sqlite3 todo.db "CREATE TABLE task (
    name TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES project (project_id),
    done BOOLEAN NOT NULL DEFAULT FALSE)"
```

1. **Install audite on your sytem**
    ```sh
    python3 -m pip install audite
    ```
2. **Enable audite on your database**
    ```sh
    python3 -m audite todo.db
    ```

Done! From now on, any process can `INSERT`, `UPDATE`, and `DELETE` from your
database as usual, and audite's triggers will store the results as [change
events](#event-schema) in the `audite_changefeed` table. All (and only)
committed transactions will appear in the change feed.

## Modfying data and querying the change feed

We'll add a project and two tasks...

```sh
sqlite3 todo.db "INSERT INTO project (id, name) VALUES (1, 'goals')"
sqlite3 todo.db "INSERT INTO task (project_id, name) VALUES (1, 'try audite'), (1, 'profit')"
```

cross one task off the list...
```sh
sqlite3 todo.db "UPDATE task SET done = TRUE WHERE name = 'try audite'"
```

and cancel the other:
```sh
sqlite3 todo.db "DELETE FROM task WHERE name = 'profit'"
```

### Now let's see what changed:
```sh
sqlite3 todo.db "SELECT * FROM audite_changefeed ORDER BY id"
```

You should get back something like this:
```
id  source   subject     type             time        specversion  data                                                                                                     
--  -------  ----------  ---------------  ----------  -----------  ---------------------------------------------------------------------------------------------------------
1   project  1           project.created  1669730365  1.0          {"new":{"name":"goals","id":1}}                                                                          
2   task     try audite  task.created     1669730374  1.0          {"new":{"project_id":1,"done":0,"name":"try audite"}}                                                    
3   task     profit      task.created     1669730374  1.0          {"new":{"project_id":1,"done":0,"name":"profit"}}                                                        
4   task     try audite  task.updated     1669730381  1.0          {"new":{"project_id":1,"done":1,"name":"try audite"},"old":{"project_id":1,"done":0,"name":"try audite"}}
5   task     profit      task.deleted     1669730386  1.0          {"old":{"project_id":1,"done":0,"name":"profit"}}                                                        
```

## Event Schema
The event schema follows the [CloudEvents
spec](https://github.com/cloudevents/spec) so that other systems can easily
handle events from yours.

- `id` uniquely identifies the event with a monotonically increasing integer.
- `source` is name of the database table that changed.
- `subject` is the primary key of the database row that changed.
- `type` describes the type of change: `*.created`, `*.updated`, or `*.deleted`.
- `time` is the Unix time when the change was committed.
- `specversion` is the verion of the [CloudEvents spec](https://github.com/cloudevents/spec) in use, currently `1.0`.
- `data` is a JSON snapshot of the row that changed. The `data.new` object holds the post-change values and is present for `*.created` and `*.updated` events. The `data.old` object holds pre-change values and is present for `*.updated` and `*.deleted` events.

**Note:** Audite stores `id` and `time` as integers so that SQLite can store
and sort them efficiently, but the CloudEvents spec mandates strings. To query
events that conform exactly to the [CloudEvents JSON
spec](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md),
select from the `audite_cloudevent` view instead of the underlying
`audite_changefeed` table:

```sh
sqlite3 todo.db "SELECT cloudevent FROM audite_cloudevent ORDER BY id"
```
```
cloudevent                                                                                                                                                                                                                                                                                                            
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
{"id":"1","sequence":"00000000000000000001","source":"project","subject":"1","type":"project.created","time":"2022-11-29T13:59:25+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"name":"goals","id":1}}}                                                                             
{"id":"2","sequence":"00000000000000000002","source":"task","subject":"try audite","type":"task.created","time":"2022-11-29T13:59:34+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"project_id":1,"done":0,"name":"try audite"}}}                                                    
{"id":"3","sequence":"00000000000000000003","source":"task","subject":"profit","type":"task.created","time":"2022-11-29T13:59:34+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"project_id":1,"done":0,"name":"profit"}}}                                                            
{"id":"4","sequence":"00000000000000000004","source":"task","subject":"try audite","type":"task.updated","time":"2022-11-29T13:59:41+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"new":{"project_id":1,"done":1,"name":"try audite"},"old":{"project_id":1,"done":0,"name":"try audite"}}}
{"id":"5","sequence":"00000000000000000005","source":"task","subject":"profit","type":"task.deleted","time":"2022-11-29T13:59:46+00:00","specversion":"1.0","datacontenttype":"application/json","data":{"old":{"project_id":1,"done":0,"name":"profit"}}}                                                            
```

## Handling database schema changes
When your database schema changes, you need to re-run audite for the triggers to
pick up the latest fields. It's safe to re-run audite multiple times, including
as part of your schema migration scripts or even on app startup.

When your database schema hasn't changed, then re-running audite does nothing.
When your schema _has_ changed, then re-running audite rebuilds the triggers to
write to the change feed with the latest schema.

## Auditing only particular tables
By default, audite tracks all tables in the target database. But you can specify
tables to track via the `--table` argument:

```sh
python3 -m audite blog.db --table post --table comment
```

## Dependencies
Audite is a python package with no dependencies. You need Python >= 3.7 to
enable audite on a database, but because "enable audite on a database" just
means "add some SQL triggers," you don't need Python after the triggers are
installed.


## Prior Art
- [litestream](https://litestream.io/blog/why-i-built-litestream/) by
  @benbjohnson makes a convincing case for using SQLite in production.
- [supa_audit](https://github.com/supabase/supa_audit) by @supabase
  demonstrates how easy change feeds can be in Postgres.
- [marmot](https://github.com/maxpert/marmot) by @maxpert uses schema
  introspection and triggers that directly inspired the approach here.
