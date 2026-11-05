import ast
import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def functions(relative, names, **context):
    source=ast.parse((ROOT/relative).read_text(encoding="utf-8"))
    nodes=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)]
    nodes.extend(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names)
    namespace={"pd":pd,"datetime":datetime,"sys":sys,**context}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),relative,"exec"),namespace)
    return namespace

class MigrationTests(unittest.TestCase):
    def test_latest_price_queries_latest_trading_date(self):
        sdk=Mock()
        sdk.get_last_trade_date.return_value="20261104"
        sdk.get_stock_daily.return_value=pd.DataFrame([{"symbol":"000001.SZ","date":"20261104","close":12.5}])
        ns=functions("scripts/signal_store.py",{"get_latest_price_for_stock"})
        with patch.dict(sys.modules,{"panda_data":sdk}),patch.dict("os.environ",{"DEFAULT_USERNAME":"test-user","DEFAULT_PASSWORD":"test-password","JAVA_SERVICE_BASE_URL":"https://example.invalid"},clear=True):
            self.assertEqual(ns["get_latest_price_for_stock"]("000001"),12.5)
        params=sdk.get_stock_daily.call_args.kwargs
        self.assertEqual((params["start_date"],params["end_date"]),("20261104","20261104"))
        self.assertEqual(params["symbol"],["000001.SZ"])

if __name__ == "__main__":
    unittest.main()
