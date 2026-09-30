"""
PDF Generator for Room Rent Management App
Generates payment receipts and full annual statements.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import io
from datetime import datetime
from xml.sax.saxutils import escape

# Color palette
PRIMARY    = colors.HexColor('#1a3c6e')
SECONDARY  = colors.HexColor('#2563eb')
ACCENT     = colors.HexColor('#f59e0b')
SUCCESS    = colors.HexColor('#16a34a')
DANGER     = colors.HexColor('#dc2626')
LIGHT_GRAY = colors.HexColor('#f3f4f6')
MID_GRAY   = colors.HexColor('#9ca3af')
WHITE      = colors.white

def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle('Title2', parent=s['Title'],
        textColor=PRIMARY, fontSize=18, leading=22, spaceAfter=2))
    s.add(ParagraphStyle('Subtitle', parent=s['Normal'],
        textColor=SECONDARY, fontSize=11, leading=14, spaceAfter=4))
    s.add(ParagraphStyle('Header', parent=s['Normal'],
        textColor=WHITE, fontSize=10, leading=14, alignment=TA_CENTER))
    s.add(ParagraphStyle('Cell', parent=s['Normal'],
        fontSize=9, leading=12))
    s.add(ParagraphStyle('CellRight', parent=s['Normal'],
        fontSize=9, leading=12, alignment=TA_RIGHT))
    s.add(ParagraphStyle('SmallGray', parent=s['Normal'],
        fontSize=8, textColor=MID_GRAY))
    s.add(ParagraphStyle('BigAmount', parent=s['Normal'],
        fontSize=15, textColor=PRIMARY, leading=18, alignment=TA_CENTER))
    return s

def _header_block(styles, client, receipt_no, year, month_name=None):
    """Builds the top header section (logo area + client info)."""
    elements = []

    # Title bar
    title_text = '33 ROOM RENT MANAGEMENT'
    elements.append(Paragraph(title_text, styles['Title2']))
    sub = month_name or str(year)
    elements.append(Paragraph(f'Payment Receipt — {sub} {year}', styles['Subtitle']))
    elements.append(HRFlowable(width='100%', thickness=2, color=PRIMARY, spaceAfter=8))

    # Two-column info table
    now = datetime.now().strftime('%d %b %Y  %H:%M')
    info_data = [
        [Paragraph('<b>CLIENT DETAILS</b>', styles['Cell']),
         Paragraph('<b>RECEIPT INFO</b>', styles['Cell'])],
        [Paragraph(f"<b>ID :</b>  #{client['id']:04d}", styles['Cell']),
         Paragraph(f"<b>Receipt No :</b>  {receipt_no}", styles['Cell'])],
        [Paragraph(f"<b>Name :</b>  {client['name']}", styles['Cell']),
         Paragraph(f"<b>Date :</b>  {now}", styles['Cell'])],
        [Paragraph(f"<b>Mobile :</b>  {client['mobile'] or '—'}", styles['Cell']),
         Paragraph(f"<b>Year :</b>  {year}", styles['Cell'])],
        [Paragraph(f"<b>Room :</b>  {client['room_no'] or 'Room 33'}", styles['Cell']),
         Paragraph(f"<b>Monthly Rent :</b>  AED {client['monthly_rent']:.0f}", styles['Cell'])],
    ]
    t = Table(info_data, colWidths=[9*cm, 9*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), LIGHT_GRAY),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('FONT', (0,0), (-1,0), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.4*cm))
    return elements

def create_receipt_pdf(data, year, month, month_names):
    """Generate a single-month payment receipt PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = _styles()
    elements = []

    client = data['client']
    month_name = month_names[month]
    receipt_no = f"RCT-{client['id']:04d}-{year}-{month.upper()}"
    payment = data['payments'].get(month, {})

    elements += _header_block(styles, client, receipt_no, year, month_name)

    # ── Payment for this month
    elements.append(Paragraph(f'<b>PAYMENT — {month_name.upper()} {year}</b>', styles['Cell']))
    elements.append(Spacer(1, 0.2*cm))

    paid    = payment.get('amount_paid', 0)
    due     = payment.get('amount_due', client['monthly_rent'])
    balance = payment.get('balance', due)

    month_data = [
        [Paragraph('<b>Month</b>', styles['Header']),
         Paragraph('<b>Amount Due</b>', styles['Header']),
         Paragraph('<b>Amount Paid</b>', styles['Header']),
         Paragraph('<b>Balance</b>', styles['Header']),
         Paragraph('<b>Date Paid</b>', styles['Header']),
         Paragraph('<b>Method</b>', styles['Header'])],
        [Paragraph(f'{month_name} {year}', styles['Cell']),
         Paragraph(f'AED {due:.2f}', styles['CellRight']),
         Paragraph(f'AED {paid:.2f}', styles['CellRight']),
         Paragraph(f'AED {balance:.2f}', styles['CellRight']),
         Paragraph(payment.get('paid_date') or '—', styles['Cell']),
         Paragraph(payment.get('payment_method') or '—', styles['Cell'])],
    ]
    t = Table(month_data, colWidths=[3.5*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
        ('PADDING', (0,0), (-1,-1), 8),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('BACKGROUND', (0,1), (-1,1), LIGHT_GRAY),
        ('TEXTCOLOR', (3,1), (3,1), DANGER if balance > 0 else SUCCESS),
        ('FONT', (3,1), (3,1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.5*cm))

    # ── Annual summary
    elements.append(Paragraph(f'<b>ANNUAL BALANCE SUMMARY — {year}</b>', styles['Cell']))
    elements.append(Spacer(1, 0.2*cm))

    old_bal = data.get('old_balance', 0)
    rows = [[
        Paragraph('<b>Month</b>', styles['Header']),
        Paragraph('<b>Due</b>', styles['Header']),
        Paragraph('<b>Paid</b>', styles['Header']),
        Paragraph('<b>Balance</b>', styles['Header']),
    ]]

    if old_bal != 0:
        rows.append([
            Paragraph('Old Balance', styles['Cell']),
            Paragraph('', styles['Cell']),
            Paragraph('', styles['Cell']),
            Paragraph(f'AED {old_bal:.2f}', styles['CellRight']),
        ])

    from app import MONTHS
    for m in MONTHS:
        p = data['payments'].get(m)
        if not p:
            continue
        bal_color = DANGER if p['balance'] > 0 else SUCCESS
        rows.append([
            Paragraph(month_names[m], styles['Cell']),
            Paragraph(f"AED {p['amount_due']:.2f}", styles['CellRight']),
            Paragraph(f"AED {p['amount_paid']:.2f}", styles['CellRight']),
            Paragraph(f"AED {p['balance']:.2f}", styles['CellRight']),
        ])

    total_bal = data['total_balance']
    rows.append([
        Paragraph('<b>TOTAL BALANCE</b>', styles['Cell']),
        Paragraph(f"<b>AED {data['total_due']:.2f}</b>", styles['CellRight']),
        Paragraph(f"<b>AED {data['total_paid']:.2f}</b>", styles['CellRight']),
        Paragraph(f"<b>AED {total_bal:.2f}</b>", styles['CellRight']),
    ])

    t2 = Table(rows, colWidths=[5*cm, 4*cm, 4*cm, 4*cm])
    style_cmds = [
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#dbeafe')),
        ('FONT', (0,-1), (-1,-1), 'Helvetica-Bold'),
    ]
    # Alternate rows
    for i in range(1, len(rows)-1):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0,i), (-1,i), LIGHT_GRAY))
    t2.setStyle(TableStyle(style_cmds))
    elements.append(t2)
    elements.append(Spacer(1, 0.8*cm))

    # ── Total balance highlight
    bal_color_hex = '#dc2626' if total_bal > 0 else '#16a34a'
    bal_label = 'OUTSTANDING BALANCE' if total_bal > 0 else 'ACCOUNT CLEAR ✓'
    elements.append(Paragraph(
        f'<font color="{bal_color_hex}"><b>{bal_label}: AED {total_bal:.2f}</b></font>',
        styles['BigAmount']
    ))

    # ── Footer
    elements.append(Spacer(1, 1*cm))
    elements.append(HRFlowable(width='100%', thickness=1, color=MID_GRAY))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph(
        'This is a computer-generated receipt. Thank you for your payment.',
        styles['SmallGray']
    ))

    doc.build(elements)
    return buffer.getvalue()


def create_full_statement_pdf(data, year, months, month_names):
    """Generate a full annual statement PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = _styles()
    elements = []

    client = data['client']
    receipt_no = f"STMT-{client['id']:04d}-{year}"

    elements += _header_block(styles, client, receipt_no, year, 'Annual Statement')

    client_notes = (client.get('notes') or '').strip()
    if client_notes:
        elements.append(Paragraph(
            f'<b>Client Notes:</b> {escape(client_notes).replace(chr(10), "<br/>")}',
            styles['Cell']
        ))
        elements.append(Spacer(1, 0.2*cm))

    elements.append(Paragraph(f'<b>COMPLETE PAYMENT RECORD — {year}</b>', styles['Cell']))
    elements.append(Spacer(1, 0.2*cm))

    rows = [[
        Paragraph('<b>Month</b>', styles['Header']),
        Paragraph('<b>Due</b>', styles['Header']),
        Paragraph('<b>Paid</b>', styles['Header']),
        Paragraph('<b>Balance</b>', styles['Header']),
        Paragraph('<b>Status</b>', styles['Header']),
        Paragraph('<b>Notes</b>', styles['Header']),
    ]]

    old_bal = data.get('old_balance', 0)
    if old_bal != 0:
        rows.append([
            Paragraph('Old Balance B/F', styles['Cell']),
            Paragraph('—', styles['CellRight']),
            Paragraph('—', styles['CellRight']),
            Paragraph(f'AED {old_bal:.2f}', styles['CellRight']),
            Paragraph('Carried Forward', styles['Cell']),
            Paragraph('', styles['Cell']),
        ])

    for m in months:
        p = data['payments'].get(m)
        if not p:
            continue
        status = '✅ Paid' if p['balance'] <= 0 else f'⚠️ Due AED {p["balance"]:.0f}'
        rows.append([
            Paragraph(month_names[m], styles['Cell']),
            Paragraph(f"AED {p['amount_due']:.2f}", styles['CellRight']),
            Paragraph(f"AED {p['amount_paid']:.2f}", styles['CellRight']),
            Paragraph(f"AED {p['balance']:.2f}", styles['CellRight']),
            Paragraph(status, styles['Cell']),
            Paragraph(escape((p.get('notes') or '').strip()).replace('\n', '<br/>'), styles['Cell']),
        ])

    total_bal = data['total_balance']
    rows.append([
        Paragraph('<b>TOTAL</b>', styles['Cell']),
        Paragraph(f"<b>AED {data['total_due']:.2f}</b>", styles['CellRight']),
        Paragraph(f"<b>AED {data['total_paid']:.2f}</b>", styles['CellRight']),
        Paragraph(f"<b>AED {total_bal:.2f}</b>", styles['CellRight']),
        Paragraph(
            '<b>CLEAR ✓</b>' if total_bal <= 0 else f'<b>BALANCE DUE</b>',
            styles['Cell']
        ),
        Paragraph('', styles['Cell']),
    ])

    t = Table(rows, colWidths=[2.2*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.3*cm, 5*cm])
    style_cmds = [
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
        ('PADDING', (0,0), (-1,-1), 7),
        ('ALIGN', (1,0), (3,-1), 'RIGHT'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#dbeafe')),
        ('FONT', (0,-1), (-1,-1), 'Helvetica-Bold'),
    ]
    for i in range(1, len(rows)-1):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0,i), (-1,i), LIGHT_GRAY))
    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 0.8*cm))

    bal_label = 'TOTAL OUTSTANDING BALANCE' if total_bal > 0 else 'ACCOUNT FULLY SETTLED ✓'
    bal_color_hex = '#dc2626' if total_bal > 0 else '#16a34a'
    elements.append(Paragraph(
        f'<font color="{bal_color_hex}"><b>{bal_label}: AED {total_bal:.2f}</b></font>',
        styles['BigAmount']
    ))

    elements.append(Spacer(1, 1*cm))
    elements.append(HRFlowable(width='100%', thickness=1, color=MID_GRAY))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph(
        f'Statement generated on {datetime.now().strftime("%d %B %Y at %H:%M")}',
        styles['SmallGray']
    ))

    doc.build(elements)
    return buffer.getvalue()
