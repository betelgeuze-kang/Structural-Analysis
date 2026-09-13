# A1 force exports: rounded conversion hypothesis

This read-only follow-up to [the lineage audit](aci-peer-history-lineage-20260913.md)
compares the same sealed ACI record 272 and PEER record 201. It introduces no
new specimens, training rows, solver runs, source correction or admission.

Both original SHA-256 values were checked against the lineage receipt before
reading the 866 ordered pairs. Using Decimal arithmetic at precision 60:

- `PEER force in kN * Decimal('0.2248')` equals the ACI force exactly in 10 rows.
- Rounding that product to each original ACI force token's decimal exponent
  reproduces **all 866 ACI force values** (Decimal round-half-even).
- The maximum unrounded difference is **0.000000004624 kip**.

This is a stronger descriptive explanation than fitting an arbitrary scale:
the fixed rounded factor accounts for every printed force value. It remains
a hypothesis about export history. The actual exporter implementation and its
conversion rule have not been authenticated. The acquired resource HTML links
site scripts, but does not itself establish a force conversion algorithm.
Do not substitute this factor for a standard unit definition, rewrite either
source, or infer which export preceded the other.

The earlier exact displacement agreement and specimen attribution still mean
these records must not be treated as independent train/test cases. Source reuse
terms, complete specimen reconstruction and compatibility with the current
physical model remain separate unresolved admission conditions.

The executed [audit script](../../scripts/audit_aci_peer_a1_force_rounding.py)
requires the two original files as positional arguments and checks their fixed
SHA-256 values before parsing. Its [machine result](aci-peer-rounded-force-hypothesis-20260914.summary.json)
preserves the counts and explicit non-admission flags. It writes JSON to stdout
and never alters the input files. Reproduction uses the original paths in the
linked lineage receipt; the core arithmetic is:

```python
from decimal import Decimal, localcontext

# aci_force_tokens and peer_force_tokens retain the source's ordered strings.
with localcontext() as context:
    context.prec = 60
    context.rounding = 'ROUND_HALF_EVEN'
    assert len(aci_force_tokens) == len(peer_force_tokens) == 866
    for aci_token, peer_token in zip(aci_force_tokens, peer_force_tokens):
        aci = Decimal(aci_token)
        quantum = Decimal(1).scaleb(aci.as_tuple().exponent)
        proposed_export = Decimal(peer_token) * Decimal('0.2248')
        assert proposed_export.quantize(quantum) == aci
```

This is an arithmetic consistency check of two acquired files, not independent
experimental verification or evidence of learned runtime savings.
