import functools
import sqlite3
import threading
import typing

import click

name_id = typing.Union[str, int]


class Database(threading.local):
    INIT = """
    CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS tag_files(tag_id INTEGER, file_id INTEGER);
    CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, name TEXT, path TEXT);
    CREATE TABLE IF NOT EXISTS options(name TEXT UNIQUE, value);
    CREATE TABLE IF NOT EXISTS selections(name TEXT UNIQUE, value TEXT);
    """

    CURSOR_TYPES = {}

    def __init__(self, db, *args, **kwargs):
        self._db = sqlite3.connect(db, *args, **kwargs)
        self._db.executescript(self.INIT)
        self._db.commit()

    def cursor(self):
        return _BaseCursor(self._db)

    def __getattr__(self, item):
        c = self.cursor()
        v = getattr(c, item)

        if not callable(v):
            return v

        @functools.wraps(v)
        def wr(*args, **kwargs):
            with c:
                return v(*args, **kwargs)

        return wr


class _BaseCursor:
    def __init__(self, db):
        if isinstance(db, _BaseCursor):
            self._db = db._db
            self._c = db._c

        else:
            self._db = db
            self._c = db.cursor()

        self.execute = self._c.execute
        self.fetchone = self._c.fetchone
        self.fetchall = self._c.fetchall
        self.fetchmany = self._c.fetchmany
        self.executescript = self._c.executescript
        self.__iter__ = self._c.__iter__
        self.close = self._c.close
        self.commit = self._db.commit

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __init_subclass__(cls, **kwargs):
        Database.CURSOR_TYPES[cls.ATTR_NAME] = cls

    def _fetch_first(self):
        return [i[0] for i in self.fetchall()]

    def __getattr__(self, item):
        if item == 'fetch_first':
            return self._fetch_first

        v = Database.CURSOR_TYPES.get(item)
        if v is None:
            raise AttributeError('%r object has no attribute %r' % (self.__class__.__name__, item))
        return v(self)


class _SelectionsCursor(_BaseCursor):
    ATTR_NAME = 'selections'

    @click.argument('name')
    @click.argument('value')
    def new(self, name: str, value: str):
        """Create new selection"""
        self.execute("INSERT INTO selections(name, value) VALUES(?, ?)", (name, value))
        self.commit()
        return True

    @click.argument('name')
    def remove(self, name: str):
        """Remove selection by name or id"""
        self.execute("DELETE FROM selections WHERE name = ?", (name, ))
        self.commit()
        return True

    def all_names(self):
        """Show all selection names"""
        self.execute("SELECT name FROM selections;")
        return self.fetch_first()

    @click.argument('src')
    @click.argument('dst')
    def rename(self, src: str, dst: str):
        """Change name of tag from old (may be id) to new"""
        if '__ALL__' in (src, dst):
            return False

        self.execute("UPDATE selections SET name = ? WHERE name = ?", (dst, src))
        self.commit()
        return True

    @click.argument('name')
    def resolve(self, name: str):
        """Return value of selection"""
        self.execute("SELECT value FROM selections WHERE name = ?", (name, ))
        c = self.fetchone()
        return None if c is None else c[0]

    @click.argument('name')
    def select(self, name: str):
        """Return all elements matches selection"""
        self.execute("SELECT files.name FROM tag_files INNER JOIN files ON files.id = tag_files.file_id INNER JOIN tags"
                     " ON tags.id = tag_files.tag_id WHERE %s" % self.resolve(name))
        return self.fetch_first()

    @click.argument('name')
    def exists(self, name: str):
        """Return true if selection exists"""
        return self.resolve(name) is not None

    @click.argument('name')
    @click.argument('file')
    def matches(self, name: str, file: name_id):
        """Return true if selection contains file"""
        if isinstance(file, int):
            self.execute("SELECT files.name FROM tag_files INNER JOIN files ON files.id = tag_files.file_id INNER JOIN "
                         "tags ON tags.id = tag_files.tag_id WHERE files.id = ? AND %s" % self.resolve(name), (file, ))
        else:
            self.execute("SELECT files.name FROM tag_files INNER JOIN files ON files.id = tag_files.file_id INNER JOIN "
                         "tags ON tags.id = tag_files.tag_id WHERE files.name = ? AND %s" % self.resolve(name), (file,))
        c = self.fetchone()
        return c is not None


class _OptionsCursor(_BaseCursor):
    ATTR_NAME = 'options'

    @click.argument('name')
    @click.argument('value')
    def set(self, name: str, value):
        """Set filesystem option"""
        self.execute("INSERT OR REPLACE INTO options(name, value) VALUES(?, ?)", (name, value))
        self.commit()

    @click.argument('name')
    def get(self, name: str):
        """Get filesystem option"""
        self.execute("SELECT value FROM options WHERE name = ?", (name, ))
        c = self.fetchone()
        return None if c is None else c[0]

    @click.argument('name')
    def unset(self, name: str):
        """Remove filesystem option"""
        self.execute("REMOVE FROM options WHERE name = ?", (name, ))
        self.commit()


class _TagsCursor(_BaseCursor):
    ATTR_NAME = 'tags'

    @click.argument('name')
    def new(self, name: str):
        """Create new tag"""
        if name == '__ALL__':
            return False

        self.execute("INSERT INTO tags(name) VALUES (?)", (name, ))
        self.commit()
        return True

    @click.argument('name')
    def remove(self, name: name_id):
        """Remove tag by name or id"""
        if name == '__ALL__':
            return False

        i = self.get_id(name)

        self.execute("DELETE FROM tag_files WHERE tag_id = ?", (i, ))
        self.execute("DELETE FROM tags WHERE id = ?", (i, ))
        self.commit()
        return True

    @click.argument('name')
    def get_id(self, name: name_id):
        """Return tag id by name (or id)"""
        if isinstance(name, int):
            return name
        if name == '__ALL__':
            return -1

        self.execute("SELECT id FROM tags WHERE name = ?", (name,))
        c = self.fetchone()
        return None if c is None else c[0]

    @click.argument('name')
    def get_name(self, name: name_id):
        """Return name of tag by id (or name)"""
        if isinstance(name, str):
            return name

        self.execute("SELECT name FROM tags WHERE id = ?", (name,))
        c = self.fetchone()
        return None if c is None else c[0]

    def all_names(self):
        """Show all tag names"""
        self.execute("SELECT name FROM tags;")
        return self.fetch_first()

    def all_ids(self):
        """Show all tag ids"""
        self.execute("SELECT id FROM tags;")
        return self.fetch_first()

    @click.argument('src')
    @click.argument('dst')
    def rename(self, src: name_id, dst: str):
        """Change name of tag from old (may be id) to new"""
        if '__ALL__' in (src, dst):
            return False

        if isinstance(src, int):
            self.execute("UPDATE tags SET name = ? WHERE id = ?", (dst, src))
        else:
            self.execute("UPDATE tags SET name = ? WHERE name = ?", (dst, src))

        self.commit()
        return True

    @click.argument('name')
    def exists(self, name: name_id):
        """Return true if tag exists"""
        return self.get_id(name) is not None


class _FilesCursor(_BaseCursor):
    ATTR_NAME = 'files'

    @click.argument('name')
    @click.argument('path')
    def new(self, name: str, path: str):
        """Create new file link"""
        self.execute("INSERT INTO files(name, path) VALUES (?, ?)", (name, path))
        self.commit()
        return True

    @click.argument('name')
    def remove(self, name: name_id):
        """Remove file link by name or id"""
        i = self.get_id(name)

        self.execute("DELETE FROM tag_files WHERE file_id = ?", (i, ))
        self.execute("DELETE FROM files WHERE id = ?", (i, ))
        self.commit()
        return True

    @click.argument('name')
    def get_id(self, name: name_id):
        """Return id of file by name (or id)"""
        if isinstance(name, int):
            return name

        self.execute("SELECT id FROM files WHERE name = ?", (name,))
        c = self.fetchone()
        return None if c is None else c[0]

    @click.argument('name')
    def get_name(self, name: name_id):
        """Return name of file by id (or name)"""
        if isinstance(name, str):
            return name

        self.execute("SELECT name FROM files WHERE id = ?", (name,))
        c = self.fetchone()
        return None if c is None else c[0]

    def all_names(self):
        """Return all files names"""
        self.execute("SELECT name FROM files;")
        return self.fetch_first()

    def all_ids(self):
        """Return all files ids"""
        self.execute("SELECT id FROM files;")
        return self.fetch_first()

    @click.argument('src')
    @click.argument('dst')
    def rename(self, src: name_id, dst: str):
        """Rename file from old (may be id) to new"""
        if isinstance(src, int):
            self.execute("UPDATE files SET name = ? WHERE id = ?", (dst, src))
        else:
            self.execute("UPDATE files SET name = ? WHERE name = ?", (dst, src))

        self.commit()
        return True

    @click.argument('name')
    def exists(self, name: name_id):
        """Return true if exists"""
        return self.get_id(name) is not None

    @click.argument('tag')
    def get_by_tag(self, tag: name_id):
        """Return all file name with given tag (name or id)"""
        if tag == '__ALL__':
            return self.all_names()

        t = self.tags.get_id(tag)
        self.execute("SELECT files.name FROM files INNER JOIN tag_files ON tag_files.file_id = files.id WHERE "
                     "tag_files.tag_id = ?", (t, ))
        return self.fetch_first()

    @click.argument('name')
    @click.argument('tag')
    def add_tag(self, name: name_id, tag: name_id):
        """Add tag to file"""
        if tag == '__ALL__':
            return False

        self.execute("INSERT INTO tag_files(tag_id, file_id) VALUES(?, ?)",
                     (self.tags.get_id(tag), self.get_id(name)))
        self.commit()
        return True

    @click.argument('name')
    @click.argument('tag')
    def remove_tag(self, name: name_id, tag: name_id):
        """Remove tag from file"""
        if tag == '__ALL__':
            return False

        self.execute("DELETE FROM tag_files WHERE tag_id = ? AND file_id = ?",
                     (self.tags.get_id(tag), self.get_id(name)))
        self.commit()
        return True

    @click.argument('name')
    @click.argument('tag')
    def has_tag(self, name: name_id, tag: name_id):
        """Return true if file has tag"""
        if tag in ('__ALL__', -1):
            return True

        self.execute("SELECT tag_id FROM tag_files WHERE tag_id = ? AND file_id = ?",
                     (self.tags.get_id(tag), self.get_id(name)))
        return len(self.fetch_first()) > 0

    @click.argument('name')
    def resolve(self, name: name_id):
        """Return path of file"""
        if isinstance(name, int):
            self.execute("SELECT path FROM files WHERE id = ?", (name, ))
        else:
            self.execute("SELECT path FROM files WHERE name = ?", (name, ))

        c = self.fetchone()
        return None if c is None else c[0]

    @click.argument('name')
    def get_tags(self, name: name_id):
        """Return all tags of file"""
        name = self.get_id(name)
        self.execute("SELECT tags.name FROM tag_files INNER JOIN tags ON tags.id = tag_files.tag_id WHERE"
                     " tag_files.file_id = ?", (name, ))
        return self.fetch_first()

    @click.argument('name')
    @click.argument('tags', nargs=-1)
    def set_tags(self, name: name_id, tags: typing.List[name_id]):
        """Replace tags of file"""
        name = self.get_id(name)
        self.execute("DELETE FROM tag_files WHERE file_id = ?", (name, ))

        t = self.tags
        for tag in tags:
            i = t.get_id(tag)
            if i is None:
                t.new(tag)
                i = t.get_id(tag)

            self.execute("INSERT INTO tag_files(tag_id, file_id) VALUES(?, ?)", (i, name))

        self.commit()
        return True
