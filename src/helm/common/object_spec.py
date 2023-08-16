import importlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Type


@dataclass(frozen=True)
class ObjectSpec:
    """Specifies how to construct an object."""

    # Class name of an object
    class_name: str

    # Arguments used to construct the scenario
    args: Dict[str, Any]

    def __hash__(self):
        return hash((self.class_name, tuple((k, self.args[k]) for k in sorted(self.args.keys()))))


def get_class_by_name(full_class_name: str) -> Type[Any]:
    components = full_class_name.split(".")
    class_name = components[-1]
    module_name = ".".join(components[:-1])
    return getattr(importlib.import_module(module_name), class_name)


def create_object(spec: ObjectSpec, additional_args: Optional[Dict[str, Any]] = None):
    """Create the actual object given the `spec`."""
    cls = get_class_by_name(spec.class_name)
    args = {}
    args.update(spec.args)
    if additional_args:
        key_collisions = set(args.keys()) & set(additional_args.keys())
        if key_collisions:
            raise ValueError(f"Argument name collisions {key_collisions} when trying to create object of class {spec.class_name}")
        args.update(additional_args)
    return cls(**args)


def parse_object_spec(description: str) -> ObjectSpec:
    """
    Parse `description` into an `ObjectSpec`.
    `description` has the format:
        <class_name>:<key>=<value>,<key>=<value>
    Usually, the description is something that's succinct and can be typed on the command-line.
    Here, value defaults to string.
    """

    def parse_arg(arg: str) -> Tuple[str, Any]:
        if "=" not in arg:
            raise ValueError(f"Expected <key>=<value>, got '{arg}'")
        value: Any
        key, value = arg.split("=", 1)

        # Try to convert to number
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass

        return (key, value)

    if ":" in description:
        name, args_str = description.split(":", 1)
        args: Dict[str, Any] = dict(parse_arg(arg) for arg in args_str.split(","))
    else:
        name = description
        args = {}
    return ObjectSpec(name, args)
