# Prior art and intended contribution

QuadAudit does not introduce numerical quadrature, adversarial integrands, error-estimator assessment, parameterized test families, or automatic benchmark reports.

- Gonnet reviews adaptive error estimation and compares methods across established families and batteries, including failures and work. [Review](https://arxiv.org/html/1003.4629), [reliability paper](https://arxiv.org/html/1006.3962)
- The author's QUADCC distribution includes a multi-integrator comparison suite and report generation. [Distribution](https://www.mathworks.com/matlabcentral/fileexchange/35489-quadcc)
- SciPy's QUADPACK tests already compare actual error with reported error and exercise specialized modes. [Tests](https://github.com/scipy/scipy/blob/main/scipy/integrate/tests/test_quadpack.py)
- Burkardt TEST_INT supplies a common integrand/domain/reference interface. Some routines named EXACT return estimated decimal values; importing these as certified references would be wrong without further work. [Source](https://people.sc.fsu.edu/~jburkardt/f_src/test_int/test_int.f90)
- Modern QUADPACK requests improved tests and reference values. Exportable exact fixtures may provide concrete upstream value. [Repository](https://github.com/jacobwilliams/quadpack)
- mpmath documents difficulties with oscillation, narrow features and interval splitting. Its high-precision answer is not an oracle by agreement alone. [Versioned source and documentation](https://github.com/mpmath/mpmath/blob/1.3.0/mpmath/calculus/quadrature.py)
- FLINT/python-flint provides ball arithmetic and integration. Its callback must respect analyticity; the documentation demonstrates erroneous answers when this is violated. We defer that reference class. [Integration contract](https://python-flint.readthedocs.io/en/latest/acb.html#flint.acb.integral)

The intended contribution is a small portable mathematical representation and auditable experiment protocol that combines exact oracles, conservative classification, applicability, enforced scalar evaluation caps, reproducible raw evidence, and useful regression exports across independent implementations. Usefulness and adoption must be demonstrated, not inferred from repository size.

A bounded name search on 2026-09-30 found no GitHub repository matching quadaudit and a 404 at PyPI's quadaudit JSON endpoint. This is neither reservation nor trademark clearance.
