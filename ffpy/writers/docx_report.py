"""Export calculation results into a formatted Microsoft Word (.docx) report."""

import os
from ffpy.outparse import parse_out, parse_text

try:
    import docx
    from docx import Document
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Inches, Pt, RGBColor
except ImportError:
    docx = None


def is_docx_available():
    """Return True if python-docx is installed and can be imported."""
    return docx is not None


def _require_docx():
    if docx is None:
        raise ImportError(
            "Для экспорта отчёта в формат .docx требуется библиотека python-docx.\n"
            "Установите её командой: pip install python-docx"
        )


def _set_cell_background(cell, hex_color):
    """Set the background color of a table cell (e.g. 'F2F4F7')."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def _set_cell_margins(cell, top=100, bottom=100, start=140, end=140):
    """Set cell margins in dxa (1 pt = 20 dxa)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in (('top', top), ('bottom', bottom), ('left', start), ('right', end)):
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def _format_table(table, alignments=None, header_bg="EDF2F7", zebra_bg="F8FAFC"):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(table.rows):
        # Repeat header on new pages & prevent row split across pages
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
        if i == 0:
            trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

        for j, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_margins(cell, top=100, bottom=100, start=140, end=140)

            # Shading
            if i == 0 and header_bg:
                _set_cell_background(cell, header_bg)
            elif i > 0 and zebra_bg and (i % 2 == 1):
                _set_cell_background(cell, zebra_bg)

            # Alignment
            if alignments and j < len(alignments):
                for p in cell.paragraphs:
                    p.alignment = alignments[j]
                    if i == 0:
                        for run in p.runs:
                            run.font.bold = True


def generate_report(out_or_data, docx_path=None):
    """Generate a .docx report from a .out filepath or parsed data dictionary.

    Parameters
    ----------
    out_or_data : str, os.PathLike, or dict
        Path to the .out file or dictionary from parse_out() / parse_text().
    docx_path : str or None
        Target path for the .docx file. If None and out_or_data is a file path,
        <stem>.docx is used.

    Returns
    -------
    str : Path to the created .docx file.
    """
    _require_docx()

    if isinstance(out_or_data, (str, os.PathLike)):
        out_path = os.fspath(out_or_data)
        data = parse_out(out_path)
        if docx_path is None:
            docx_path = os.path.splitext(out_path)[0] + ".docx"
    elif isinstance(out_or_data, dict):
        data = out_or_data
        if docx_path is None:
            docx_path = "report.docx"
    else:
        raise TypeError(f"Expected file path or dict, got {type(out_or_data)}")

    write_docx(docx_path, data)
    return docx_path


def write_docx(docx_path, data):
    """Write parsed calculation data to a .docx document."""
    _require_docx()

    doc = Document()

    # Document-wide default styles
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    # Document Header / Title
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(2)
    run_title = title_p.add_run("Отчёт о квантово-химическом расчёте")
    run_title.font.name = 'Calibri'
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(12)
    run_sub = sub_p.add_run("Программа: ffpy (PySCF backend)")
    run_sub.font.size = Pt(10)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Section 1: General Info
    h1 = doc.add_heading("1. Общие сведения", level=1)
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(4)

    status_str = "✔ Завершён нормально" if data.get("normal") else (
        f"✖ Ошибка (код {data.get('exit_code')}: {data.get('error')})" if data.get("exit_code") is not None
        else "… Расчёт не завершён"
    )

    info_rows = [
        ("Заголовок задачи", str(data.get("title") or "—")),
        ("Метод", str(data.get("method") or "—")),
        ("Базисный набор", str(data.get("basis") or "—")),
        ("Тип расчёта (RUNTYP)", str(data.get("runtyp") or "—")),
        ("Статус расчёта", status_str),
    ]
    if data.get("wall_time") is not None:
        info_rows.append(("Время выполнения", f"{data['wall_time']:.2f} с"))

    t_info = doc.add_table(rows=len(info_rows), cols=2)
    t_info.style = 'Table Grid'
    for r_idx, (k, v) in enumerate(info_rows):
        row = t_info.rows[r_idx]
        p0 = row.cells[0].paragraphs[0]
        r0 = p0.add_run(k)
        r0.font.bold = True
        p1 = row.cells[1].paragraphs[0]
        p1.add_run(v)
    _format_table(t_info, alignments=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT],
                  header_bg=None, zebra_bg="F8FAFC")

    # Section 2: Energetics
    h2 = doc.add_heading("2. Энергетические характеристики", level=1)
    h2.paragraph_format.space_before = Pt(14)
    h2.paragraph_format.space_after = Pt(4)

    energy_rows = []
    if data.get("energy") is not None:
        energy_rows.append(("Полная энергия (E_tot)", f"{data['energy']:.10f}", "Hartree"))
    if data.get("scf") is not None:
        energy_rows.append(("Энергия SCF / DFT", f"{data['scf']:.10f}", "Hartree"))
    if data.get("mp2") is not None:
        energy_rows.append(("Энергия MP2", f"{data['mp2']:.10f}", "Hartree"))
    if data.get("dipole") is not None:
        energy_rows.append(("Дипольный момент (|μ|)", f"{data['dipole']:.4f}", "Debye"))

    if energy_rows:
        t_en = doc.add_table(rows=len(energy_rows) + 1, cols=3)
        t_en.style = 'Table Grid'
        hdr = t_en.rows[0]
        for c_idx, title in enumerate(["Параметр", "Значение", "Единицы"]):
            hdr.cells[c_idx].paragraphs[0].add_run(title)

        for r_idx, (param, val, unit) in enumerate(energy_rows):
            row = t_en.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(param)
            row.cells[1].paragraphs[0].add_run(val)
            row.cells[2].paragraphs[0].add_run(unit)

        _format_table(t_en, alignments=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.CENTER])
    else:
        p = doc.add_paragraph("Данные об энергии отсутствуют.")
        p.paragraph_format.space_after = Pt(4)

    # Section 3: Geometry
    h3 = doc.add_heading("3. Геометрия молекулы", level=1)
    h3.paragraph_format.space_before = Pt(14)
    h3.paragraph_format.space_after = Pt(4)

    geom = data.get("geometry") or []
    if geom:
        p_sub = doc.add_paragraph()
        p_sub.paragraph_format.space_after = Pt(3)
        r = p_sub.add_run("Координаты атомов (Å):")
        r.font.bold = True

        t_geo = doc.add_table(rows=len(geom) + 1, cols=5)
        t_geo.style = 'Table Grid'
        ghdr = t_geo.rows[0]
        for c_idx, title in enumerate(["Атом", "Z", "X (Å)", "Y (Å)", "Z (Å)"]):
            ghdr.cells[c_idx].paragraphs[0].add_run(title)

        for r_idx, item in enumerate(geom):
            row = t_geo.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(str(item.get("atom", "")))
            z_val = item.get("Z") if item.get("Z") is not None else item.get("z", "")
            row.cells[1].paragraphs[0].add_run(f"{z_val:.1f}" if isinstance(z_val, (int, float)) else str(z_val))
            row.cells[2].paragraphs[0].add_run(f"{item.get('x', 0.0):.6f}")
            row.cells[3].paragraphs[0].add_run(f"{item.get('y', 0.0):.6f}")
            z_coord = item.get("z") if "z" in item and item is not z_val else item.get("z_coord", 0.0)
            row.cells[4].paragraphs[0].add_run(f"{z_coord:.6f}")

        _format_table(t_geo, alignments=[
            WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT
        ])

    bonds = data.get("bonds") or {}
    if bonds:
        p_b = doc.add_paragraph()
        p_b.paragraph_format.space_before = Pt(8)
        p_b.paragraph_format.space_after = Pt(3)
        r = p_b.add_run("Межатомные расстояния (длины связей):")
        r.font.bold = True

        t_bonds = doc.add_table(rows=len(bonds) + 1, cols=2)
        t_bonds.style = 'Table Grid'
        bhdr = t_bonds.rows[0]
        bhdr.cells[0].paragraphs[0].add_run("Связь")
        bhdr.cells[1].paragraphs[0].add_run("Длина (Å)")
        for r_idx, ((a, b), dist) in enumerate(bonds.items()):
            row = t_bonds.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(f"{a} – {b}")
            row.cells[1].paragraphs[0].add_run(f"{dist:.4f}")
        _format_table(t_bonds, alignments=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT])

    angles = data.get("angles") or {}
    if angles:
        p_a = doc.add_paragraph()
        p_a.paragraph_format.space_before = Pt(8)
        p_a.paragraph_format.space_after = Pt(3)
        r = p_a.add_run("Валентные углы:")
        r.font.bold = True

        t_ang = doc.add_table(rows=len(angles) + 1, cols=2)
        t_ang.style = 'Table Grid'
        ahdr = t_ang.rows[0]
        ahdr.cells[0].paragraphs[0].add_run("Угол")
        ahdr.cells[1].paragraphs[0].add_run("Величина (°)")
        for r_idx, ((a, b, c), val) in enumerate(angles.items()):
            row = t_ang.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(f"{a} – {b} – {c}")
            row.cells[1].paragraphs[0].add_run(f"{val:.2f}")
        _format_table(t_ang, alignments=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT])

    # Section 4: Atomic Charges (Mulliken and Lowdin)
    h4 = doc.add_heading("4. Заряды на атомах", level=1)
    h4.paragraph_format.space_before = Pt(14)
    h4.paragraph_format.space_after = Pt(4)

    mulliken = data.get("mulliken") or {}
    lowdin = data.get("lowdin") or {}
    all_atoms = list(mulliken.keys()) or list(lowdin.keys())

    if all_atoms:
        has_lowdin = bool(lowdin)
        cols = 3 if has_lowdin else 2
        t_chg = doc.add_table(rows=len(all_atoms) + 2, cols=cols)
        t_chg.style = 'Table Grid'

        chdr = t_chg.rows[0]
        chdr.cells[0].paragraphs[0].add_run("Атом")
        chdr.cells[1].paragraphs[0].add_run("Заряд Малликена (e)")
        if has_lowdin:
            chdr.cells[2].paragraphs[0].add_run("Заряд Лёвдина (e)")

        m_sum, l_sum = 0.0, 0.0
        for r_idx, atom in enumerate(all_atoms):
            row = t_chg.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(atom)
            m_val = mulliken.get(atom)
            if m_val is not None:
                row.cells[1].paragraphs[0].add_run(f"{m_val:.4f}")
                m_sum += m_val
            else:
                row.cells[1].paragraphs[0].add_run("—")

            if has_lowdin:
                l_val = lowdin.get(atom)
                if l_val is not None:
                    row.cells[2].paragraphs[0].add_run(f"{l_val:.4f}")
                    l_sum += l_val
                else:
                    row.cells[2].paragraphs[0].add_run("—")

        tot_row = t_chg.rows[-1]
        p_tot = tot_row.cells[0].paragraphs[0].add_run("Сумма (TOTAL)")
        p_tot.font.bold = True
        p_m = tot_row.cells[1].paragraphs[0].add_run(f"{m_sum:.4f}")
        p_m.font.bold = True
        if has_lowdin:
            p_l = tot_row.cells[2].paragraphs[0].add_run(f"{l_sum:.4f}")
            p_l.font.bold = True

        aligns = [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT] if has_lowdin else [
            WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT
        ]
        _format_table(t_chg, alignments=aligns)
    else:
        p = doc.add_paragraph("Данные популяционного анализа отсутствуют.")
        p.paragraph_format.space_after = Pt(4)

    # Section 5: Frequencies
    freqs = data.get("freqs") or []
    if freqs:
        h5 = doc.add_heading("5. Колебательные частоты", level=1)
        h5.paragraph_format.space_before = Pt(14)
        h5.paragraph_format.space_after = Pt(4)

        ir_km = data.get("ir_km") or []
        t_freq = doc.add_table(rows=len(freqs) + 1, cols=3)
        t_freq.style = 'Table Grid'
        fhdr = t_freq.rows[0]
        fhdr.cells[0].paragraphs[0].add_run("№ моды")
        fhdr.cells[1].paragraphs[0].add_run("Частота (см⁻¹)")
        fhdr.cells[2].paragraphs[0].add_run("ИК-интенсивность (км/моль)")

        for r_idx, f in enumerate(freqs):
            row = t_freq.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(str(r_idx + 1))
            f_str = f"{abs(f):.2f} i" if f < 0 else f"{f:.2f}"
            row.cells[1].paragraphs[0].add_run(f_str)
            ir_val = ir_km[r_idx] if r_idx < len(ir_km) else None
            row.cells[2].paragraphs[0].add_run(f"{ir_val:.2f}" if ir_val is not None else "—")

        _format_table(t_freq, alignments=[
            WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT
        ])

    # Section 6: Excited States
    excited = data.get("excited") or []
    if excited:
        h6 = doc.add_heading("6. Возбуждённые состояния", level=1)
        h6.paragraph_format.space_before = Pt(14)
        h6.paragraph_format.space_after = Pt(4)

        t_ex = doc.add_table(rows=len(excited) + 1, cols=4)
        t_ex.style = 'Table Grid'
        ehdr = t_ex.rows[0]
        ehdr.cells[0].paragraphs[0].add_run("Состояние")
        ehdr.cells[1].paragraphs[0].add_run("Энергия (эВ)")
        ehdr.cells[2].paragraphs[0].add_run("Длина волны (нм)")
        ehdr.cells[3].paragraphs[0].add_run("Сила осциллятора (f)")

        for r_idx, s in enumerate(excited):
            row = t_ex.rows[r_idx + 1]
            row.cells[0].paragraphs[0].add_run(str(s.get("state", r_idx + 1)))
            row.cells[1].paragraphs[0].add_run(f"{s.get('ev', 0.0):.3f}")
            row.cells[2].paragraphs[0].add_run(f"{s.get('nm', 0.0):.1f}")
            row.cells[3].paragraphs[0].add_run(f"{s.get('f', 0.0):.4f}")

        _format_table(t_ex, alignments=[
            WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT,
            WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT
        ])

    target_dir = os.path.dirname(os.path.abspath(docx_path))
    os.makedirs(target_dir, exist_ok=True)
    doc.save(docx_path)
