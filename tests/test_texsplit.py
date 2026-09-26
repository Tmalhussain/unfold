from unfold.texsplit import split_symbols


def test_symbols_isolated_outside_control_words():
    parts = split_symbols(r"\exp(x) + \text{max x}", ["x"])
    assert parts.count("x") == 1  # only the argument of exp, not inside \exp or \text{}


def test_longest_symbol_wins_and_scripts_stay_attached():
    parts = split_symbols(r"\hat{m}_t + m_t", ["m_t", r"\hat{m}_t", "m"])
    assert r"\hat{m}_t" in parts and "m_t" in parts
    assert "".join(parts).replace(" ", "").count("{") == "".join(parts).replace(" ", "").count("}")


def test_no_double_brace_openers_created():
    for p in split_symbols(r"{x}^2 + \frac{x}{2}", ["x"]):
        assert not p.startswith("{{") and "}}" not in p.replace("} }", "")


def test_equals_split_only_at_top_level():
    parts = split_symbols(r"S = \frac{a=b}{2}", [], split_equals=True)
    assert parts.count("=") == 1
