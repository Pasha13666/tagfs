import sys

import click
import fuse

from tagfs.db import Database
from tagfs.ops import TagFS


@click.group('tagfs', context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('database', type=click.Path(exists=True, dir_okay=False, writable=True))
@click.pass_context
def tagfs(ctx, database):
    ctx.obj = Database(database)


class DatabaseElementCli(click.MultiCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._commands_lz = None

    @property
    def _commands(self):
        if self._commands_lz is None:
            self._obj = getattr(click.get_current_context().obj, self.name)
            self._commands_lz = {i: getattr(self._obj.__class__, i) for i in dir(self._obj.__class__)
                                 if not i.startswith('_') and i.islower()}
        return self._commands_lz

    def list_commands(self, ctx):
        return list(sorted(self._commands.keys()))

    def get_command(self, ctx, cmd_name):
        def _command_wrapper(*args, **kwargs):
            v = self._commands[cmd_name](self._obj, *args, **kwargs)
            if v is not None:
                click.echo(v)

        cmd = click.command(cmd_name)(self._commands[cmd_name])
        cmd.callback = _command_wrapper
        return cmd


class DatabaseCli(click.MultiCommand):
    def __init__(self, *args, item_args=(), item_kwargs=None, **kwargs):
        super().__init__(*args, **kwargs)

        self._names = list(sorted(Database.CURSOR_TYPES.keys()))
        self._obj = None
        self._args = item_args
        self._kwargs = {} if item_kwargs is None else item_kwargs

    def list_commands(self, ctx):
        return self._names

    def get_command(self, ctx, cmd_name):
        if self._obj is None:
            self._obj = click.get_current_context().obj

        return DatabaseElementCli(getattr(self._obj, cmd_name), name=cmd_name, *self._args, **self._kwargs)


def mount():
    kw = {}

    while True:
        for i, v in enumerate(sys.argv):
            if v == '-o' or v.startswith('-o'):
                break
        else:
            break

        if sys.argv[i] == '-o':
            options = sys.argv[i + 1]
            del sys.argv[i]
            del sys.argv[i]

        else:
            options = sys.argv[i][2:]
            del sys.argv[i]

        for i in options.split(','):
            i = i.strip()
            n = i.find('=')
            if n == -1:
                kw[i] = True
            else:
                kw[i[:n]] = i[n+1:]

    print(sys.argv, kw)
    db = Database(sys.argv[1])
    fuse.FUSE(TagFS(db, kw.pop('base_dir', '.')), sys.argv[2], raw_fi=False, **kw)


for name in Database.CURSOR_TYPES:
    tagfs.add_command(DatabaseElementCli(name=name))


if __name__ == '__main__':
    tagfs()
