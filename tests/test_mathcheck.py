from unfold.mathcheck import check_derived, normalize


def test_normalize_ignores_spacing_and_script_braces():
    assert normalize(r"m_{t} = \beta_1 \, m_{t-1}") == normalize(r"m_t=\beta_1 m_{t-1}")
    assert normalize(r"\left( x \right) \label{eq:a}") == normalize("(x)")


def test_derived_checks():
    assert check_derived(r"(a+b)^2 = a^2 + 2ab + b^2", "identity")[0] == "verified"
    assert check_derived(r"(a+b)^2 = a^2 + b^2", "identity")[0] == "FAILED"
    assert (
        check_derived(r"s = 2 - \frac{1}{2^{n-1}}", {"at": {"n": 3}, "value": 1.75})[0]
        == "verified"
    )
    assert check_derived(r"x = 1", None)[0] == "unchecked"
