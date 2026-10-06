def test_scenes_get_numpy_but_no_other_modules_or_helpers():
    import types

    from unfold import style

    names = {n: getattr(style, n) for n in style.__all__}
    assert [n for n, v in names.items() if isinstance(v, types.ModuleType)] == ["np"]
    assert "Circle" in names and not {"capture", "open_file", "config", "logger"} & set(names)


def test_segment_box_crossing():
    import numpy as np

    from unfold.style import _crosses

    box = (0.0, 0.0, 2.0, 1.0)
    through, above, grazing = (np.array([-1.0, y]) for y in (0.5, 2.0, 0.05))
    assert _crosses(through, through + [4.0, 0], box)
    assert not _crosses(above, above + [4.0, 0], box)
    assert not _crosses(grazing, grazing + [4.0, 0], box)  # only touches the padding
