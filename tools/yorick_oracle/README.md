# Yorick cost reference data

`backend/tests/fixtures/yorick_vampire_costs.json.gz` holds Yorick's answer to
"what does this trait cost?" for 13,952 combinations of clan, extra in-clan
disciplines, generation, category, trait, rating and free rating. Horatio's
Vampire rule set must give the same answer for every one
(`backend/tests/test_vampire_costs_match_yorick.py`).

It was produced by running Yorick's own cost engine, not a re-implementation of
it. To regenerate it from a Yorick checkout:

```bash
node --experimental-strip-types --no-warnings vampire_costs_oracle.mts \
  ../yorick/client/src/domain/rules/BNSMETV1_VampireCosts.ts \
  ../yorick/data/bnsmetv1_clan_rule.csv \
  | gzip -9 > backend/tests/fixtures/yorick_vampire_costs.json.gz
```

Needs Node 22.6 or later. `BNSMETV1_VampireCosts.ts` has no imports, so it
runs on its own.
