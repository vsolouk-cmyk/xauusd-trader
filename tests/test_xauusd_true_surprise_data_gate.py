import json, tempfile, unittest
from pathlib import Path
import pandas as pd
from app.xauusd_true_surprise_data_gate import validate, parse_number

class Tests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_number('250K'),250000)
        self.assertEqual(parse_number('3.2%'),3.2)
    def test_full_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inbox=root/'in'; out=root/'out'; inbox.mkdir()
            rows=[]
            groups=[('Inflation Rate MoM','%'),('Core Inflation Rate MoM','%'),('Non Farm Payrolls','K')]
            cal=1
            for ev,unit in groups:
                dates=pd.date_range('2016-01-15', periods=84, freq='MS', tz='UTC') + pd.Timedelta(days=12,hours=13,minutes=30)
                for d in dates:
                    rows.append({'CalendarId':str(cal),'Date':d.isoformat(),'Country':'United States','Event':ev,'Actual':'1.1' if unit=='%' else '200K','Previous':'1.0' if unit=='%' else '190K','Forecast':'1.0' if unit=='%' else '195K','DateSpan':'0','Importance':'3','LastUpdate':(d+pd.Timedelta(minutes=1)).isoformat(),'Unit':unit})
                    cal+=1
            pd.DataFrame(rows).to_csv(inbox/'te.csv',index=False)
            cfg={'program':'x','reference_start_utc':'2016-01-01T00:00:00Z','reference_end_utc':'2025-01-01T00:00:00Z','country':'United States','required_event_groups':{'CPI_HEADLINE_MOM':['Inflation Rate MoM'],'CPI_CORE_MOM':['Core Inflation Rate MoM'],'NFP':['Non Farm Payrolls']},'minimum_valid_rows_per_group':80,'required_columns':['CalendarId','Date','Country','Event','Actual','Previous','Forecast','DateSpan','Importance','LastUpdate','Unit'],'point_in_time_rules':{}}
            cp=root/'cfg.json'; cp.write_text(json.dumps(cfg))
            s=validate(inbox,cp,out)
            self.assertTrue(s['pass']); self.assertEqual(s['valid_rows'],252)
            self.assertTrue((out/'true_surprise_events_normalized.csv').exists())
    def test_reject_missing_forecast(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inbox=root/'in'; out=root/'out'; inbox.mkdir()
            pd.DataFrame([{'CalendarId':'1','Date':'2020-01-01T13:30:00Z','Country':'United States','Event':'Inflation Rate MoM','Actual':'1','Previous':'1','Forecast':'','DateSpan':'0','Importance':'3','LastUpdate':'2020-01-01T13:31:00Z','Unit':'%'}]).to_csv(inbox/'x.csv',index=False)
            cfg={'reference_start_utc':'2016-01-01T00:00:00Z','reference_end_utc':'2025-01-01T00:00:00Z','country':'United States','required_event_groups':{'CPI_HEADLINE_MOM':['Inflation Rate MoM']},'minimum_valid_rows_per_group':1,'required_columns':['CalendarId','Date','Country','Event','Actual','Previous','Forecast','DateSpan','Importance','LastUpdate','Unit']}
            cp=root/'cfg.json'; cp.write_text(json.dumps(cfg)); s=validate(inbox,cp,out); self.assertFalse(s['pass'])
if __name__=='__main__': unittest.main()
