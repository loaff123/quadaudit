# The core-v1 exact-reference corpus

Core-v1 is **504 original synthetic cases: 72 cases in each of seven classical
archetypes**. This is a small, reviewable, rational piecewise-polynomial domain.
It is not 504 independent numerical mechanisms, a sample of real scientific
workloads, or a claim that these classical formulas are new.

The corpus constructors, design stream, parameter choices, exact coefficient
arithmetic, tests, and JSONL are original project work. No third-party test code,
dataset, prose, or figures were copied. Primary mathematical references are
linked below; formulas describe standard mathematics.

## Coordinates and the stored representation

Every construction uses `x = offset + width*t`, where `0 <= t <= 1`, `width > 0`,
and `f(x) = amplitude*g(t)`. Thus a normalized area `I` becomes
`amplitude*width*I`. Affine changes and amplitude scales are **modifiers**.

A stored segment `[l,r]` contains exact rational coefficients in the local
coordinate `v=(x-l)/(r-l)`. All intervals are contiguous and cover the declared
domain. Compact beta and spline profiles include explicit zero segments on each
side of their support when applicable. Interior knots select the **right-hand
segment**; the final domain endpoint selects the final segment. These point
values do not affect the integral.

The seven archetypes intentionally overlap as broad classes of polynomials and
piecewise polynomials. They are distinguished by their construction identities
and stress mechanisms, not asserted statistical independence. No two frozen
cases are the same mathematical function on the same domain, even after
removing metadata, redundant zero powers, and redundant subdivisions.

## Family definitions and area proofs

### 1. Power controls: `power`

`g(t)=t^n`, with `0 <= n <= 16`. Its normalized area is `1/(n+1)`, from the
antiderivative `t^(n+1)/(n+1)`. The constant case is retained as a simple control.
These cases expose basic degree, domain-scale, and amplitude-scale behavior.
The coefficient constructor sets a single nonzero power; point tests evaluate
the defining power directly.

### 2. Beta-polynomial profiles: `beta`

On support `[L,R]`, write `u=(t-L)/(R-L)`. Set
`g(t)=u^p*(1-u)^q` there and zero elsewhere, with positive integer `p,q` and
`p+q <= 16`. The normalized area is

`(R-L) * p! q! / (p+q+1)!`.

Repeated integration by parts gives
`J(p,q)=q/(p+1)*J(p+1,q-1)` and `J(p+q,0)=1/(p+q+1)`, proving the factorial
identity independently of the expanded coefficients. This is also Euler's beta
integral at integer arguments ([NIST DLMF 5.12.1](https://dlmf.nist.gov/5.12#E1)).
The builder uses a binomial expansion; tests use the factored defining function.
Full-domain and translated narrow supports retain the same family label.

### 3. Shifted Legendre polynomials: `legendre`

`g(t)=P_n(2t-1)`, `1 <= n <= 16`, has normalized area zero. The shifted
Rodrigues identity is

`P_n(2t-1) = (1/n!) * d^n/dt^n [t^n(t-1)^n]`.

Integrating once gives the difference of the `(n-1)`st derivatives at the two
endpoints. Each is zero because both endpoints are roots of order `n`. The
coefficient builder instead uses the three-term recurrence. Exact point tests
use the distinct binomial formula
`sum_{k=0}^n binom(n,k)^2 t^k (t-1)^(n-k)`.

These are signed-area cancellation controls. Their zero reference is exact,
not a high-precision estimate ([DLMF definitions](https://dlmf.nist.gov/18.3),
[explicit representations](https://dlmf.nist.gov/18.5),
[recurrences](https://dlmf.nist.gov/18.9)).

### 4. Even shifted Chebyshev polynomials: `chebyshev_even`

`g(t)=T_(2n)(2t-1)`, `1 <= n <= 8`, has normalized area `1/(1-4n^2)`.
Set `2t-1=cos(theta)`. The integral is
`(1/2)*integral_0^pi cos(2n*theta)*sin(theta) dtheta`; product-to-sum reduces it
to the stated rational value. The defining trigonometric identity appears in
[DLMF 18.5.1](https://dlmf.nist.gov/18.5#E1).

The builder uses `T_m(z)=2z*T_(m-1)(z)-T_(m-2)(z)`. Tests use the independent
finite factorial expansion in powers of `z`. Only even degrees appear here so
these oscillatory signed profiles have a nonzero reference, distinct from the
zero-area Legendre identity.

### 5. Rational staircases: `staircase`

For an increasing partition `0=b_0<...<b_s=1`, set `g(t)=h_j` on the `j`th
interval. The area is the rectangle sum `sum_j h_j*(b_(j+1)-b_j)`. At an interior
breakpoint use the next height; at `t=1` use the last height. Frozen cases have
2, 4, 8, 16, 32, or 64 equal-width pieces, with paired positive and negative
heights and a controlled final residual. These exercise discontinuities, exact
cancellation, and near cancellation. Different residuals remain modifiers.

### 6. Truncated-power hinges: `hinge`

`g(t)=max(t-c,0)^m`, with `0<c<1` and `1<=m<=16`. The left piece is zero; the
right piece is a degree-`m` power. Substitution `u=t-c` on `[c,1]` proves the
area `(1-c)^(m+1)/(m+1)`. The case is `C^(m-1)` but generally not `C^m` at the
hinge. No non-polynomial endpoint singularities are claimed.

### 7. Cardinal B-splines: `cardinal_bspline`

Let `N_d(u)` be the `(d+1)`-fold convolution of the unit-box indicator on
`[0,1)`. Its support is `[0,d+1]` and its integral is one, since integrating a
convolution multiplies the factors' unit integrals. The equivalent truncated
power representation is

`N_d(u) = (1/d!) * sum_(j=0)^(d+1) (-1)^j binom(d+1,j) max(u-j,0)^d`.

For support `[L,R]`, define `g(t)=N_d((d+1)*(t-L)/(R-L))`. Consequently its
normalized area is **`(R-L)/(d+1)`**, not one. A physical width `d+1` on full
normalized support restores unit mass. Tests check that identity for every
supported degree, and check values using the independent Cox-de Boor recurrence.
The constructor expands only active truncated powers on each knot span.

The frozen degree choices are 1, 3, 7, and 15, making the `d+1` equal knot spans
dyadic. The general constructor supports degrees 1 through 16; non-dyadic custom
knots may be unsupported by binary64 adapters. Classical definitions and the
convolution/truncated-power equivalence are described by
[Carl de Boor's cardinal B-spline notes](https://pages.cs.wisc.edu/~deboor/toast/pages005.html).

## The frozen design

The seed is `20260930`. A deterministic SHA-256 integer stream chooses among
explicit finite parameter grids; its full rule is in the manifest and
`corpus.py`. This avoids relying on interpreter-specific random sampling
implementation details. Integer-stream modular selection is a reproducible
design device, not a claim of unbiased statistical sampling.

- 72 cases per family; fixed IDs `<family>-000` through `<family>-071`
- Domain widths: `2^-6, 2^-2, 1, 2^2, 2^4, 2^6`
- Domain offsets: eighth-integers from `-2` through `2`
- Signed amplitude powers spanning `2^-40` through `2^40`
- Beta/spline support widths: `1, 2^-4, 2^-12, 2^-20` of the domain, with
  translated interior placement for compact supports
- Staircases: paired heights with final residual `0, 1/16, -1/64, 1/4096`
- Hinge positions: interior multiples of `1/64`
- Maximum polynomial degree 16; maximum 64 segments

All 504 cases have dyadic, distinct, exactly binary64-representable breakpoints.
A mathematical duplicate causes resampling before the case is admitted. The
function fingerprint expands to global rational powers, trims trailing zero
coefficients, and coalesces adjacent identical polynomials. Domain boundaries
remain part of the fingerprint. Metadata, case IDs, and equivalent subdivision
choices cannot manufacture distinct functions.

## Three exact checks, plus independent point tests

1. A family-level area identity supplies the stored reference without calling
   either polynomial integration path
2. `Case.integral()` integrates each local polynomial exactly
3. `oracle.audit_case()` independently expands each local polynomial into global
   `x` powers and integrates exact endpoint powers

The corpus verifier requires all applicable references to agree. It also checks
that known-family parameters actually describe the represented polynomial.
That reconstruction is a consistency check, **not** an independent formula
proof. The tests supply the additional independent formula-level evaluations at
rational points, including knots and each segment interior. Tests also reject
corrupted references, coefficients, parameters, duplicate IDs, and mathematically
duplicate representations.

These checks do not constitute an external expert certification or a proof that
all software defects are impossible. Exact rational arithmetic removes rounding
from the reference calculations; it does not remove the need to review the
formulas and code.

## Storage, regeneration, and the experiment freeze

The authoritative corpus is `src/quadaudit/data/core-v1.jsonl`. It is ordered
UTF-8 JSONL with sorted keys, compact separators, canonical rational strings,
and a final newline. The packaged manifest/protocol have identical repository
copies in `corpus/manifest.json` and `corpus/protocol.json`.

Run from the repository root:

```sh
PYTHONPATH=src python corpus/freeze.py
PYTHONPATH=src python -m unittest discover -s tests -p test_corpus.py -v
```

The first command regenerates all artifacts in memory and verifies identical
bytes and SHA-256 hashes. `--write` explicitly replaces them and is intended
only for a deliberate new freeze before experiments; do not rewrite a frozen
corpus to match outcomes. Default `load_corpus()` also verifies the packaged
corpus hash and all exact identities. Custom JSONL is bounded and audited but
is not required to contain 504 cases. Unknown/custom family labels receive the
two coefficient-based integration checks, without a built-in family identity
claim.

The core-v1 protocol freezes **504 x 3 methods x 2 tracks = 3024 runs**:
SciPy quad, SciPy tanhsinh, and mpmath tanh-sinh; blind and split tracks; exact
absolute target `1/100000000`; total callback budget 4096; per-run timeout 10 s;
trace limit zero; mpmath precision 80 bits; SciPy maxlevel 10; mpmath maxdegree 8.
Dependency pins and remaining native settings are in the protocol. These are
planned runs, not a claim that execution succeeded. Each actual experiment
must retain its environment, settings, corpus/protocol hashes, all outcomes,
and completion status.

Every blind, multi-segment SciPy tanhsinh run is conservatively labeled
exploratory and excluded from in-contract scores. A split run shares the total
budget and gives each method the same boundaries. SciPy's absolute target is
split equally across pieces; mpmath retains its documented precision-driven
stopping rule and has no fabricated native success flag. Tiny-amplitude cases
can satisfy the absolute target even when their support is missed; this is a
consequence of the stated target and must not be presented as relative accuracy.

The exact-rounded callback performs rational evaluation first and rounds once
to the active native precision. SciPy uses binary64 (53 bits). The pinned
mpmath solver is configured for 80-bit outputs, but its quadrature routine adds
20 guard bits, so callbacks are expected at 100 bits; each run records the
precision actually observed. Numerator and denominator are not separately
rounded before division. Aggregation sums represented piece values exactly and
rounds that sum once to the configured output type.

The budget counts charged scalar callback invocations started, including repeated
points and callbacks that fail. Completed callback values are recorded separately.
A vector request exceeding remaining capacity is rejected before evaluating any
member. Attempted requests, denied batch size, wrapper callback count, and
native-reported evaluation counts remain distinct evidence fields.
