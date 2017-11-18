"""
Module for statical analysis.
"""
from jedi import debug
from jedi.parser.python import tree
from jedi.evaluate.compiled import CompiledObject


CODES = {
    'attribute-error': (1, AttributeError, 'Potential AttributeError.'),
    'name-error': (2, NameError, 'Potential NameError.'),
    'import-error': (3, ImportError, 'Potential ImportError.'),
    'type-error-too-many-arguments': (4, TypeError, None),
    'type-error-too-few-arguments': (5, TypeError, None),
    'type-error-keyword-argument': (6, TypeError, None),
    'type-error-multiple-values': (7, TypeError, None),
    'type-error-star-star': (8, TypeError, None),
    'type-error-star': (9, TypeError, None),
    'type-error-operation': (10, TypeError, None),
    'type-error-not-iterable': (11, TypeError, None),
    'type-error-isinstance': (12, TypeError, None),
    'type-error-not-subscriptable': (13, TypeError, None),
    'value-error-too-many-values': (14, ValueError, None),
    'value-error-too-few-values': (15, ValueError, None),
}


class Error(object):
    def __init__(self, name, module_path, start_pos, message=None):
        self.path = module_path
        self._start_pos = start_pos
        self.name = name
        if message is None:
            message = CODES[self.name][2]
        self.message = message

    @property
    def line(self):
        return self._start_pos[0]

    @property
    def column(self):
        return self._start_pos[1]

    @property
    def code(self):
        # The class name start
        first = self.__class__.__name__[0]
        return first + str(CODES[self.name][0])

    def __unicode__(self):
        return '%s:%s:%s: %s %s' % (self.path, self.line, self.column,
                                    self.code, self.message)

    def __str__(self):
        return self.__unicode__()

    def __eq__(self, other):
        return (self.path == other.path and self.name == other.name and
                self._start_pos == other._start_pos)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.path, self._start_pos, self.name))

    def __repr__(self):
        return '<%s %s: %s@%s,%s>' % (self.__class__.__name__,
                                      self.name, self.path,
                                      self._start_pos[0], self._start_pos[1])


class Warning(Error):
    pass


def add(node_context, error_name, node, message=None, typ=Error, payload=None):
    exception = CODES[error_name][1]
    if _check_for_exception_catch(node_context, node, exception, payload):
        return

    # TODO this path is probably not right
    module_context = node_context.get_root_context()
    module_path = module_context.py__file__()
    instance = typ(error_name, module_path, node.start_pos, message)
    debug.warning(str(instance), format=False)
    node_context.evaluator.analysis.append(instance)


def _check_for_setattr(instance):
    """
    Check if there's any setattr method inside an instance. If so, return True.
    """
    from jedi.evaluate.representation import ModuleContext
    module = instance.get_root_context()
    if not isinstance(module, ModuleContext):
        return False

    node = module.tree_node
    try:
        stmts = node.used_names['setattr']
    except KeyError:
        return False

    return any(node.start_pos < stmt.start_pos < node.end_pos
               for stmt in stmts)


def add_attribute_error(name_context, lookup_context, name):
    message = ('AttributeError: %s has no attribute %s.' % (lookup_context, name))
    from jedi.evaluate.instance import AbstractInstanceContext, CompiledInstanceName
    # Check for __getattr__/__getattribute__ existance and issue a warning
    # instead of an error, if that happens.
    typ = Error
    if isinstance(lookup_context, AbstractInstanceContext):
        slot_names = lookup_context.get_function_slot_names('__getattr__') + \
            lookup_context.get_function_slot_names('__getattribute__')
        for n in slot_names:
            if isinstance(name, CompiledInstanceName) and \
                    n.parent_context.obj == object:
                typ = Warning
                break

        if _check_for_setattr(lookup_context):
            typ = Warning

    payload = lookup_context, name
    add(name_context, 'attribute-error', name, message, typ, payload)


def _check_for_exception_catch(node_context, jedi_name, exception, payload=None):
    """
    Checks if a jedi object (e.g. `Statement`) sits inside a try/catch and
    doesn't count as an error (if equal to `exception`).
    Also checks `hasattr` for AttributeErrors and uses the `payload` to compare
    it.
    Returns True if the exception was catched.
    """
    def check_match(cls, exception):
        try:
            return isinstance(cls, CompiledObject) and issubclass(exception, cls.obj)
        except TypeError:
            return False

    def check_try_for_except(obj, exception):
        # Only nodes in try
        iterator = iter(obj.children)
        for branch_type in iterator:
            colon = next(iterator)
            suite = next(iterator)
            if branch_type == 'try' \
                    and not (branch_type.start_pos < jedi_name.start_pos <= suite.end_pos):
                return False

        for node in obj.except_clauses():
            if node is None:
                return True  # An exception block that catches everything.
            else:
                except_classes = node_context.eval_node(node)
                for cls in except_classes:
                    from jedi.evaluate import iterable
                    if isinstance(cls, iterable.AbstractSequence) and \
                            cls.array_type == 'tuple':
                        # multiple exceptions
                        for lazy_context in cls.py__iter__():
                            for typ in lazy_context.infer():
                                if check_match(typ, exception):
                                    return True
                    else:
                        if check_match(cls, exception):
                            return True

    def check_hasattr(node, suite):
        try:
            assert suite.start_pos <= jedi_name.start_pos < suite.end_pos
            assert node.type in ('power', 'atom_expr')
            base = node.children[0]
            assert base.type == 'name' and base.value == 'hasattr'
            trailer = node.children[1]
            assert trailer.type == 'trailer'
            arglist = trailer.children[1]
            assert arglist.type == 'arglist'
            from jedi.evaluate.param import TreeArguments
            args = list(TreeArguments(node_context.evaluator, node_context, arglist).unpack())
            # Arguments should be very simple
            assert len(args) == 2

            # Check name
            key, lazy_context = args[1]
            names = list(lazy_context.infer())
            assert len(names) == 1 and isinstance(names[0], CompiledObject)
            assert names[0].obj == str(payload[1])

            # Check objects
            key, lazy_context = args[0]
            objects = lazy_context.infer()
            return payload[0] in objects
        except AssertionError:
            return False

    obj = jedi_name
    while obj is not None and not isinstance(obj, (tree.Function, tree.Class)):
        if isinstance(obj, tree.Flow):
            # try/except catch check
            if obj.type == 'try_stmt' and check_try_for_except(obj, exception):
                return True
            # hasattr check
            if exception == AttributeError and obj.type in ('if_stmt', 'while_stmt'):
                if check_hasattr(obj.children[1], obj.children[3]):
                    return True
        obj = obj.parent

    return False