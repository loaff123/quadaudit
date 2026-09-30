# Original QuadAudit regression fixture; BSD-3-Clause.
# Mathematical target is a rational piecewise polynomial.
# Function evaluation is exact at each binary64 input, then rounded once.
# This costs more than ordinary floating point evaluation.
from fractions import Fraction as F
import bisect
import json
import re

CASE = json.loads('{"case_id": "beta-014", "description": "Beta-polynomial profile, optionally restricted to an explicit compact support.", "family": "beta", "parameters": {"amplitude": "-1/16", "offset": "5/8", "p": 7, "q": 2, "support_left": "4095/65536", "support_right": "4111/65536", "width": "1"}, "reference": "-1/23592960", "schema": "quadaudit.case.v1", "segments": [{"coefficients": ["0"], "left": "5/8", "right": "45055/65536"}, {"coefficients": ["0", "0", "0", "0", "0", "0", "0", "-1/16", "1/8", "-1/16"], "left": "45055/65536", "right": "45071/65536"}, {"coefficients": ["0"], "left": "45071/65536", "right": "13/8"}]}')
REFERENCE = F(CASE['reference'])
SEGMENTS = [(F(s['left']), F(s['right']), tuple(map(F,s['coefficients']))) for s in CASE['segments']]
KNOTS = [SEGMENTS[0][0]] + [s[1] for s in SEGMENTS]

def f(x):
    x = F.from_float(float(x))
    if not KNOTS[0] <= x <= KNOTS[-1]:
        raise ValueError('outside domain')
    i = min(bisect.bisect_right(KNOTS,x)-1,len(SEGMENTS)-1)
    left,right,coefficients = SEGMENTS[i]
    t = (x-left)/(right-left)
    y = F(0)
    for c in reversed(coefficients):
        y = y*t+c
    return float(y)

if __name__ == '__main__':
    from scipy.integrate import quad
    q,e = quad(f,float(KNOTS[0]),float(KNOTS[-1]))
    actual = abs(F.from_float(q)-REFERENCE)
    print({'case':CASE['case_id'],'returned':q,'reported_error':e,'exact_actual_error':str(actual)})
