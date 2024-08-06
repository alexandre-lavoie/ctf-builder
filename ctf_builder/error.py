import abc
import dataclasses
import datetime
import typing

import rich.console
import rich.columns
import rich.markup
import rich.panel
import rich.text
import rich.tree


@dataclasses.dataclass
class LibError(abc.ABC):
    pass


@dataclasses.dataclass
class BuildError(LibError):
    context: str
    msg: str
    error: typing.Any = dataclasses.field(default=None)


@dataclasses.dataclass
class DeployError(LibError):
    context: str
    msg: str
    error: typing.Any = dataclasses.field(default=None)


@dataclasses.dataclass
class TestError(LibError):
    context: str
    expected: str
    actual: typing.Optional[str] = dataclasses.field(default=None)
    error: typing.Any = dataclasses.field(default=None)


@dataclasses.dataclass
class ParseError(LibError):
    path: str
    expected: typing.List[str]


@dataclasses.dataclass
class SkipError(LibError):
    pass


def print_errors(
    errors: typing.Sequence[typing.Union[LibError]],
    prefix: typing.Optional[typing.List[str]] = None,
    console: typing.Optional[rich.console.Console] = None,
    elapsed_time: typing.Optional[float] = None,
) -> None:
    if not console:
        safe_console = rich.console.Console()
    else:
        safe_console = console

    header_segments = []

    if prefix:
        prefix_text = rich.markup.render(
            "[blue]:[/]".join(rich.markup.escape(section) for section in prefix)
        )
    else:
        prefix_text = None

    is_ok = True
    is_skip = False
    if not errors:
        status = "[bold green]OK[/]"
        status_color = "green"
    elif all(isinstance(error, SkipError) for error in errors):
        status = "[bold yellow]SKIP[/]"
        status_color = "yellow"
        is_skip = True
    else:
        status = "[bold red]ERROR[/]"
        status_color = "red"
        is_ok = False

    status_text = rich.markup.render(status)

    if not is_skip and elapsed_time is not None:
        time_text = rich.text.Text(
            str(datetime.timedelta(seconds=max(0, int(elapsed_time)))),
            style=status_color,
        )
    else:
        time_text = None

    header_segments = [prefix_text, time_text, status_text]

    if is_ok:
        safe_console.print(*[s for s in header_segments if s])
        return

    error_tree = rich.tree.Tree(rich.columns.Columns(header_segments))

    parse_tree = rich.tree.Tree("[red]challenge.json[/]")
    build_tree = rich.tree.Tree("[red]Build[/]")
    deploy_tree = rich.tree.Tree("[red]Deploy[/]")
    test_tree = rich.tree.Tree("[red]Test[/]")
    subtrees = [parse_tree, build_tree, deploy_tree, test_tree]

    for error in errors:
        if isinstance(error, ParseError):
            parse_tree.add(
                f"[red]{rich.markup.escape(error.path)}[/] is not {", ".join('[blue]' + v + '[/]' for v in error.expected)}"
            )
        elif isinstance(error, (BuildError, DeployError)):
            if isinstance(error, DeployError):
                target_tree = deploy_tree
            else:
                target_tree = build_tree

            error_segments = [
                rich.markup.render(
                    f"[red]{error.context}[/] {rich.markup.escape(error.msg)}"
                )
            ]

            if error.error:
                error_segments.append(
                    rich.panel.Panel(
                        rich.markup.render(
                            f"[red]{rich.markup.escape(str(error.error))}[/]"
                        ),
                        title="error",
                        style="red",
                    )
                )

            target_tree.add(rich.console.Group(*error_segments))
        elif isinstance(error, TestError):
            if error.error:
                label = rich.console.Group(
                    rich.markup.render(
                        f"[red]{error.context}[/] error for [red]{rich.markup.escape(error.expected)}[/]"
                    ),
                    rich.panel.Panel(
                        rich.markup.render(
                            f"[red]{rich.markup.escape(str(error.error))}[/]"
                        ),
                        title="error",
                        style="red",
                    ),
                )
            else:
                label = rich.markup.render(
                    f"[red]{error.context}[/] expected [red]{rich.markup.escape(error.expected)}[/] but got [red]{rich.markup.escape(error.actual) if error.actual else '<empty>'}[/]"
                )

            test_tree.add(label)
        else:
            build_tree.add(rich.markup.escape(str(error)))

    for subtree in subtrees:
        if not subtree.children:
            continue

        error_tree.add(subtree)

    safe_console.print(error_tree)


def get_exit_status(errors: typing.Sequence[typing.Union[LibError]]) -> bool:
    if not errors:
        return True

    if all(isinstance(error, SkipError) for error in errors):
        return True

    return False
