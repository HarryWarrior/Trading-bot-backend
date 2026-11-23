# analytics service

Pure KPI domain (summary, equity curve, breakdowns) over a journal dataset. HTTP layer arrives with
plan 2 task 6. Route prefix: `/api/v1/analytics`.

```bash
pip install -e "libs/shared[dev]" -e "services/analytics[dev]"
pytest services/analytics/tests -q -W error
```
