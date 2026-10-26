"""Two-page initial research report; regenerate as data matures."""
from xml.sax.saxutils import escape
import json
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from poll_rec_counts import ROOT
from datetime import datetime
from zoneinfo import ZoneInfo

def main():
    out=ROOT/'reports'
    status=json.loads((out/'status.json').read_text())
    data=pd.read_csv(out/'latest_counts.csv')
    weights=data[data.location.str.contains('Strength|Conditioning',case=False,regex=True)]
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCustom',fontName='Helvetica-Bold',fontSize=24,leading=28,textColor=colors.HexColor('#56162b'),spaceAfter=15))
    styles.add(ParagraphStyle(name='BodyCustom',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=10))
    styles.add(ParagraphStyle(name='Label',fontName='Helvetica-Bold',fontSize=12,leading=16,spaceBefore=12,spaceAfter=7,textColor=colors.HexColor('#56162b')))
    styles.add(ParagraphStyle(name='SmallCustom',fontSize=8,leading=11,spaceAfter=5))
    captured=datetime.fromisoformat(status['last_poll']).astimezone(ZoneInfo('America/Chicago'))
    stamp=captured.strftime('%Y-%m-%d %H:%M %Z')
    story=[]
    def p(text,style='BodyCustom'): story.append(Paragraph(text,styles[style]))
    p('REC SPORTS / INITIAL RESEARCH REPORT','SmallCustom')
    p('Collection has started.<br/>Capacity findings need history.','TitleCustom')
    p(f'{stamp} | Texas A&amp;M recreation occupancy | Independent analysis','SmallCustom')
    p(f'The archive contains {status["distinct_observations"]} distinct observations across {status["zones"]} zones from {status["successful_polls"]} successful polls. The three weight rooms reported the following values. They are asynchronous staff counts, not a simultaneous census or evidence of recurring peak demand.')
    table=[['Weight room','People / capacity','Reported ratio','Age at capture']]
    for r in weights.itertuples():
        label={'Student Rec Center':'SRC','Southside Rec Center':'Southside','Polo Road Rec Center':'Polo Road'}.get(r.facility,r.facility)
        table.append([label,f'{r.last_count:.0f} / {r.capacity:.0f}',f'{r.utilization:.1%}',f'{r.age_at_snapshot_min:.0f} minutes'])
    t=Table(table,colWidths=[115,125,115,125]); t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#56162b')),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),10),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f3efeb'),colors.white])]))
    story.append(t); story.append(Spacer(1,10))
    p(f'Latest capture: {stamp}. Ages refer to this capture. Counts may be closed or stale; consult the dashboard flags.','SmallCustom')
    p('The first finding is a measurement limitation','Label')
    p(f'Across archived observations, median age at first capture was {status["age_min_quantiles"]["0.5"]:.0f} minutes; {status["closed_rows"]} records were marked closed. This mix includes inactive areas and is not the sampling cadence of the weight rooms. The configured all-zero batch heuristic flagged {status["reset_rows"]} records in this capture; absence of a flag does not prove absence of resets.')
    p('What is operational today','Label')
    p('The local poller saves complete responses before validation, deduplicates observations, preserves poll-level sightings, and records failures. SQL views expose reset candidates, revisions, capacity ratios, timestamp issues and verified opening status. Published schedules have been imported for the three strength rooms; other zones remain unverified.')
    p('Scheduled collection is deployed','Label')
    p('GitHub collection has completed manual and scheduled runs. Observed schedules have substantial delays, so ten-minute collection is not yet reliable. The dashboard reports polling gaps and threshold-coverage bounds. Use an always-on collector if the observed gaps persist.')
    story.append(PageBreak())
    p('How the project will answer<br/>the capacity questions','TitleCustom')
    p('A reproducible analysis plan with explicit evidence thresholds','SmallCustom')
    p('Profiles and constraints','Label')
    p('Average within each observed hourly bin, then compare weekday/hour cells with their sample counts. Do not fill gaps. Threshold exposure carries a reading forward for at most 90 minutes and stops at the next observation, including invalid or closed observations. Intersect with published hours and report unknown coverage as lower/upper exceedance bounds. A bottleneck ranking requires comparable coverage and sufficient separation between bounds.')
    p('Forecast and semester dynamics','Label')
    p('Evaluate last-value, same-hour-last-week and fixed ridge models on the same final 14-day holdout after at least six weeks of eligible pairs. Inputs must be available at the forecast origin; score next-reading horizons of 30-120 minutes and disclose the horizon distribution. Weather forecast vintages and sourced home-game features are availability-gated to avoid future information. I-MR limits require 21 reviewed normal days; daily maxima can shift simply because sampling coverage changes.')
    p('The academic calendar lists Thanksgiving on November 26-27, finals on December 7-10, and spring classes beginning January 19, 2027. No such shifts have been observed yet. A January exponential-decay fit needs at least 28 adequately covered return-period days and residual/weekday checks before interpreting its half-life.')
    p('A what-if scenario, not an arrival estimate','Label')
    p('The implemented sensitivity transfers a selected fraction of profile occupancy person-hours from 5-7 pm to 2-4 pm while conserving total person-hours. Headcounts do not reveal arrivals, departures or visit durations. The scenario cannot establish that moving a given percentage of visitors will produce the predicted peak reduction.')
    p('Next milestones','Label')
    p('Monitor deployed collection and scheduling gaps; review quality during week one. After four continuous weeks, publish preliminary profiles and coverage. After six weeks, evaluate baseline/ridge forecasts. Review finals signals in December and January dynamics in late February. Keep unmeasured resume claims as placeholders.')
    p('Sources and reproducibility','Label')
    for label,url in [
        ('Rec Sports live counts','https://recsports.tamu.edu/facilities/live-facility-count/'),
        ('Rec Sports hours','https://recsports.tamu.edu/hours-of-operation/'),
        ('Fall 2026 academic calendar','https://registrar.tamu.edu/academic-calendar/fall-2026.html'),
        ('Spring 2027 academic calendar','https://registrar.tamu.edu/academic-calendar/spring-2027.html')]:
        p(f'<a href="{url}" color="#56162b">{escape(label)}</a> - retrieved October 22, 2026.','SmallCustom')
    p('See README.md for methods and limitations; raw/ for replayable captures; reports/ for CSVs and the portable dashboard. No forecast improvement, causal peak reduction, or semester-shift claim is made.','SmallCustom')
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8); canvas.setFillColor(colors.HexColor('#746b65'))
        canvas.drawString(54,29,'REC OCCUPANCY | PROGRESS REPORT | '+captured.strftime('%Y-%m-%d'))
        canvas.drawRightString(558,29,str(doc.page))
    doc=SimpleDocTemplate(str(out/'progress-report.pdf'),pagesize=letter,rightMargin=54,leftMargin=54,topMargin=40,bottomMargin=45)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(out/'progress-report.pdf')

if __name__=='__main__': main()
