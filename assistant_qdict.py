
class QDict():
    def __init__(self, data):
        self.data = data
        self.codecache = {}

    def find(self, path, data=None, sep='/'):
        if not data:
            data = self.data
        return self._get(path, data=data, sep=sep)

    def paths(self, path, data=None, sep='/'):
        items = self.find(path, data=data, sep=sep)
        return list(items)

    def get(self, path, data=None, sep='/'):
        items = self.find(path, data=data, sep=sep)
        return items.get(path)

    def keys(self, path, data=None, sep='/'):
        paths = self.paths(path, data=data, sep=sep)
        keys = list()
        for path in paths:
            keys.append(QDict._getDeepestKey(path, sep))
        return keys

    def uniqKeys(self, path, data=None, sep='/'):
        return set(self.keys(path, data=data, sep=sep))

    def values(self, path, data=None, sep='/'):
        items = self.find(path, data=data, sep=sep)
        return list(items.values())

    def uniqValues(self, path, data=None, sep='/'):
        return set(self.values(path, data=data, sep=sep))

    def items(self, path, data=None, sep='/'):
        results = self.find(path, data=data, sep=sep)
        items = list()
        for path, item in results.items():
            items.append((QDict._getDeepestKey(path, sep), item))
        return items

    def uniqItems(self, path, data=None, sep='/'):
        return set(self.items(path, data=data, sep=sep))

    def _get(self, path, data, parents=None, sep='/'):
        if not data:
            return dict()
        if not path:
            return data
        key, expr, rem = QDict._getKeyExprRem(path, sep)
        res = dict()
        if key == '*' or key == '**':
            if isinstance(data, dict):
                for item in data:
                    p = "'{}'[{}]".format(item, expr) if expr else "'{}'".format(item)
                    res.update(self._get(p, data=data, parents=parents, sep=sep))
            elif isinstance(data, (list, set, tuple)):
                for index, item in enumerate(data):
                    p = "'{}'[{}]".format(index, expr) if expr else "'{}'".format(index)
                    res.update(self._get(p, data=data, parents=parents, sep=sep))
        elif hasattr(data, '__iter__'):
            if key in data:
                pathkey = "'{}'".format(key) if key.find(sep) > 0 else key
                thispath = parents + sep + pathkey if parents else pathkey
                item = data[key]
                if self._evalItem(path, expr, key, item):
                    res[thispath] = item
            else:
                try:
                    if int(key) in data or data[int(key)]:
                        thispath = parents + sep + key if parents else key
                        item = data[int(key)]
                        if self._evalItem(path, expr, int(key), item):
                            res[thispath] = item
                except ValueError:
                    pass
        if not rem:
            return res
        else:
            subres = dict()
            for path, item in res.items():
                childs = self._get(rem, data=item, parents=path, sep=sep)
                if key == '**' and childs:
                    subres.update({path: item})
                else:
                    subres.update(childs)
            return subres

    def _evalExpr(self, expr, scope, cache=True):
        if cache and expr in self.codecache:
            code = self.codecache[expr]
        else:
            code = compile(expr, "<string>", "eval")
            self.codecache[expr] = code
        for name in code.co_names:
            if name not in scope:
                raise NameError("Use of '{}' not allowed in filer expressions, and the key is not found on this item. Evaluating '{}'".format(name, expr))
        return eval(code, {"__builtins__": {}}, scope)

    def _evalItem(self, path, expr, key, item):
        if not expr:
            return True
        scope = {
            "_path": path,
            "_key": key,
            "_item": item,
        }
        if isinstance(item, dict):
            for k in item.keys():
                if k in scope:
                    continue
                scope[k.replace('.', '_')] = item[k]
        try:
            return self._evalExpr(expr, scope)
        except NameError as ne:
            print("Error while evaluating expression for '{}': {}. {}".format(key, expr, ne))
        except KeyError as ke:
            print("Error while evaluating expression for '{}': {}. {}".format(key, expr, ke))
        return False

    @staticmethod
    def _getKeyExprRem(path, sep):
        key = expr = rem = ''
        if not path or path == '':
            return (key, expr, rem)
        # Key part
        quote = None
        i = 0
        for i, c in enumerate(path):
            if i == 0 and c in ('"', "'"):
                quote = c
                continue
            if quote and c == quote:
                i = i + 1
                break
            elif c == sep and not quote:
                break
            elif c == '[' and not quote:
                break
            key = key + c
        # Expression part
        if len(path) > i:
            quote = 0
            j = 0
            for j, c in enumerate(path[i:]):
                if c == '[':
                    quote = quote + 1
                    continue
                if c == ']':
                    quote = quote - 1
                    continue
                if quote < 1:
                    break
                expr = expr + c
            i = i + j
        # Remainder
        if len(path) > i:
            rem = path[i+1:]
        return (key, expr, rem)

    @staticmethod
    def _getDeepestKey(path, sep):
        key = rem = path
        while rem != '':
            key, _, rem = QDict._getKeyExprRem(rem, sep)
        return key

