"""Front end for Quack"""

from lark import Lark, Transformer
import argparse
import json
import sys

from typing import List,  Callable

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

def cli():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("source", type=argparse.FileType("r"),
                            nargs="?", default=sys.stdin)
    args = cli_parser.parse_args()
    return args


def cli():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("source", type=argparse.FileType("r"),
                            nargs="?", default=sys.stdin)
    args = cli_parser.parse_args()
    return args

LB = "{"
RB = "}"

def ignore(node: "ASTNode", visit_state):
    log.debug(f"No visitor action at {node.__class__.__name__} node")
    return

def flatten(m: list):
    """Flatten nested lists into a single level of list"""
    flat = []
    for item in m:
        if isinstance(item, list):
            flat += flatten(item)
        else:
            flat.append(item)
    return flat


class ASTNode:
    """Abstract base class"""
    def __init__(self):
        self.children = []    # Internal nodes should set this to list of child nodes

    # Visitor-like functionality for walking over the AST. Define default methods in ASTNode
    # and specific overrides in node types in which the visitor should do something
    def walk(self, visit_state, pre_visit: Callable =ignore, post_visit: Callable=ignore):
        pre_visit(self, visit_state)
        for child in flatten(self.children):
            log.debug(f"Visiting ASTNode of class {child.__class__.__name__}")
            child.walk(visit_state, pre_visit, post_visit)
        post_visit(self, visit_state)

    # Example walk to gather method signatures
    def method_table_visit(self, visit_state: dict):
        ignore(self, visit_state)

    def r_eval(self) -> List[str]:
        """Evaluate for value"""
        raise NotImplementedError(f"r_eval not implemented for node type {self.__class__.__name__}")

    def c_eval(self, true_branch: str, false_branch: str) -> List[str]:
        raise NotImplementedError(f"c_eval not implemented for node type {self.__class__.__name__}")


class ProgramNode(ASTNode):
    def __init__(self, classes: List[ASTNode], main_block: ASTNode):
        self.classes = classes
        main_class = ClassNode("$Main", [], "Obj", [], main_block)
        self.classes.append(main_class)
        self.children = self.classes

    def __str__(self) -> str:
        return "\n".join([str(c) for c in self.classes])


class ClassNode(ASTNode):
    def __init__(self, name: str, formals: List[ASTNode],
                 super_class: str,
                 methods: List[ASTNode],
                 block: ASTNode):
        self.name = name
        self.super_class = super_class
        self.methods = methods
        self.constructor = MethodNode("$constructor", formals, name, block)
        self.children = methods +  [self.constructor]

    def __str__(self):
        formals_str = ", ".join([str(fm) for fm in self.constructor.formals])
        methods_str = "\n".join([f"{method}\n" for method in self.methods])
        return f"""
        class {self.name}({formals_str}){LB}
        {methods_str}
        /* statements as a constructor */
        {self.constructor}
        {RB} /* end class {self.name} */
        """

    # Example walk to gather method signatures
    def method_table_visit(self, visit_state: dict):
        """Create class entry in symbol table (as a preorder visit)"""
        if self.name in visit_state:
            raise Exception(f"Shadowing class {self.name} is not permitted")
        visit_state["current_class"] = self.name
        visit_state[self.name] = {
            "super": self.super_class,
            "fields": [],
            "methods": {}
        }



class MethodNode(ASTNode):
    def __init__(self, name: str, formals: List[ASTNode],
                 returns: str, body: ASTNode):
        self.name = name
        self.formals = formals
        self.returns = returns
        self.body = body
        self.children = [formals, body]

    def __str__(self):
        formals_str = ", ".join([str(fm) for fm in self.formals])
        return f"""
        /* method */ 
        def {self.name}({formals_str}): {self.returns} {LB}
        {self.body}
        {RB} /* End of method {self.name} */ 
        """

    # Add this method to the symbol table
    def method_table_visit(self, visit_state: dict):
        clazz = visit_state["current_class"]
        if self.name in visit_state[clazz]["methods"]:
            raise Exception(f"Redeclaration of method {self.name} not permitted")
        params = [formal.var_type for formal in self.formals]
        visit_state[clazz]["methods"][self.name] = { "params": params, "ret": self.returns }


class FormalNode(ASTNode):
    def __init__(self, var_name: str, var_type: str):
        self.var_name = var_name
        self.var_type = var_type
        self.children = []

    def __str__(self):
        return f"{self.var_name}: {self.var_type}"


class BlockNode(ASTNode):
    def __init__(self, stmts: List[ASTNode]):
        self.stmts = stmts
        self.children = stmts

    def __str__(self):
        return "".join([str(stmt) + ";\n" for stmt in self.stmts])


class AssignmentNode(ASTNode):
    """Placeholder ... not defined in grammar yet"""
    def __init__(self, formal: ASTNode, rhs:ASTNode):

        self.lhs = formal
        self.rhs = rhs
        self.children = []

    def __str__(self):
        return f"{str( self.lhs )} = {str( self.rhs )}"


class ExprNode(ASTNode):
    """Just identifiers in this stub"""
    def __init__(self, e):
        self.e = e
        self.children = [e]

    def __str__(self):
        return str(self.e)

class MethodCallNode(ASTNode):
    """Node for calling a method"""
    def __init__(self, name: str, params: list[ ASTNode ]):
        self.name = name
        self.params = params
        self.children = params
    def __str__(self) -> str:
        ret_str = f"{self.name}("
        for i in range(len(self.params)):
            ret_str += str(self.params[i])
            if i < len(self.params) - 1:
                ret_str += ", "
        return ret_str + ")"

class VariableRefNode(ASTNode):
    """Reference to a variable in an expression.
    This will typically evaluate to a 'load' operation.
    """
    def __init__(self, name: str):
        assert isinstance(name, str)
        self.name = name
        self.children = []

    def __str__(self):
        return self.name

class IfStmtNode(ASTNode):
    def __init__(self,
                 cond: ASTNode,
                 thenpart: ASTNode,
                 elsepart: ASTNode):
        self.cond = cond
        self.thenpart = thenpart
        self.elsepart = elsepart
        self.children = [cond, thenpart, elsepart]

    def __str__(self):
        return f"""if {self.cond} {LB}\n
                {self.thenpart}
             {RB} else {LB}
                {self.elsepart} {LB}
            {RB}
            """

class CondNode(ASTNode):
    """Boolean condition. It can evaluate to jumps,
    but in this grammar it's just a placeholder.
    """
    def __init__(self, cond: str):
        self.cond = cond

    def __str__(self):
        return f"{self.cond}"



class ASTBuilder(Transformer):
    """Translate Lark tree into my AST structure"""

    def program(self, e):
        log.debug("->program")
        classes, main_block = e
        return ProgramNode(classes, main_block)

    def classes(self, e):
        return e

    def clazz(self, e):
        log.debug("->clazz")
        name, formals, super, methods, constructor = e
        return ClassNode(name, formals, super, methods, constructor)

    def methods(self, e):
        return e

    def method(self, e):
        log.debug("->method")
        name, formals, returns, body = e
        return MethodNode(name, formals, returns, body)

    def call(self, e):
        log.debug("->method call")
        return MethodCallNode(e[0], e[1:])


    def returns(self, e):
        if not e:
            return "Nothing"
        return e

    def formals(self, e):
        if e[0] is None:
            return []
        return e

    def formal(self, e):
        log.debug("->formal")
        var_name, var_type = e
        return FormalNode(var_name, var_type)

    def expr(self, e):
        log.debug("->expr")
        return ExprNode(e[0])

    def add(self, e):
        return MethodCallNode("PLUS", e)

    def sub(self, e):
        return MethodCallNode("SUB", e)

    def mul(self, e):
        return MethodCallNode("TIMES", e)

    def div(self, e):
        return MethodCallNode("DIV", e)

    def ident(self, e):
        """A terminal symbol """
        log.debug("->ident")
        return e[0]

    def variable_ref(self, e):
        """A reference to a variable"""
        log.debug("->variable_ref")
        return VariableRefNode(e[0])

    def block(self, e) -> ASTNode:
        log.debug("->block")
        stmts = e
        return BlockNode(stmts)

    def assignment(self, e) -> ASTNode:
        log.debug("->assignment")

        lhs, rhs = e
        return AssignmentNode(lhs, rhs)

    def ifstmt(self, e) -> ASTNode:
        log.debug("->ifstmt")
        cond, thenpart, elsepart = e
        return IfStmtNode(cond, thenpart, elsepart)

    def otherwise(self, e) -> ASTNode:
        log.debug("->otherwise")
        return e

    def elseblock(self, e) -> ASTNode:
        log.debug("->elseblock")
        return e[0]  # Unwrap one level of block

    def cond(self, e) -> ASTNode:
        log.debug("->cond")
        return e



def method_table_walk(node: ASTNode, visit_state: dict):
        node.method_table_visit(visit_state)

def main():
    args = cli()
    quack_parser = Lark(open("qklib/quack_grammar.txt", "r"))
    text = "".join(args.source.readlines())
    tree = quack_parser.parse(text)
    print(tree.pretty("   "))
    ast: ASTNode = ASTBuilder().transform(tree)
    print(ast)
    # Build symbol table, starting with the hard-coded json table
    # provided by Pranav.  We'll follow that structure for the rest
    builtins = open("qklib/builtin_methods.json")
    symtab = json.load(builtins)
    ast.walk(symtab, method_table_walk)
    print(json.dumps(symtab,indent=4))


if __name__ == "__main__":
    main()
