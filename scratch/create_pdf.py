import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Korean Font
font_path = "C:\\Windows\\Fonts\\malgun.ttf"
font_bold_path = "C:\\Windows\\Fonts\\malgunbd.ttf"
pdfmetrics.registerFont(TTFont('MalgunGothic', font_path))
pdfmetrics.registerFont(TTFont('MalgunGothicBold', font_bold_path))

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont('MalgunGothic', 9)
        self.setFillColor(colors.HexColor('#64748B'))
        
        # Header (Only on page 2+)
        if self._pageNumber > 1:
            self.drawString(54, 800, "AI's Eye 프론트엔드 코드 구조 & 화면 전환 흐름도")
            self.setStrokeColor(colors.HexColor('#E2E8F0'))
            self.setLineWidth(0.8)
            self.line(54, 792, 541, 792)
            
        # Footer
        footer_text = f"페이지 {self._pageNumber} / {page_count}"
        self.drawRightString(541, 36, footer_text)
        self.drawString(54, 36, "Confidential - AI's Eye Dashboard Architecture Document")
        self.setStrokeColor(colors.HexColor('#E2E8F0'))
        self.setLineWidth(0.8)
        self.line(54, 48, 541, 48)
        self.restoreState()

def build_pdf(pdf_path):
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=60,
        bottomMargin=60
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        fontName='MalgunGothicBold',
        fontSize=22,
        leading=28,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=10
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        fontName='MalgunGothic',
        fontSize=12,
        leading=18,
        textColor=colors.HexColor('#475569'),
        spaceAfter=20
    )
    
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        fontName='MalgunGothicBold',
        fontSize=15,
        leading=20,
        textColor=colors.HexColor('#065F46'),
        spaceBefore=16,
        spaceAfter=10
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        fontName='MalgunGothicBold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        fontName='MalgunGothic',
        fontSize=10,
        leading=15,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8
    )

    code_style = ParagraphStyle(
        'Code_Custom',
        fontName='MalgunGothic',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#0F172A'),
        backColor=colors.HexColor('#F8FAFC'),
        borderColor=colors.HexColor('#E2E8F0'),
        borderWidth=1,
        borderPadding=8,
        spaceAfter=10
    )

    story = []

    # Title Banner
    story.append(Paragraph("AI's Eye 프론트엔드 코드 흐름도 & 구조 가이드", title_style))
    story.append(Paragraph("메인 렌더링 → 회원가입/로그인 모달 → 매장(1,2) 대시보드 / KOS 관리 / 본사 관제 전환 명세", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#059669'), spaceAfter=15))

    # Section 1: Overview
    story.append(Paragraph("1. 프론트엔드 아키텍처 개요", h1_style))
    overview_text = (
        "<b>AI's Eye Dashboard</b> 프론트엔드는 React Single Page Application (SPA) 구조로 설계되어 있으며, "
        "단일 엔트리 포인트인 <code>App.jsx</code>를 중심으로 커스텀 훅(<code>useAuth</code>, <code>useRouting</code>, <code>useStorePolling</code>)이 "
        "인증 상태, URL 라우팅, 백엔드 API 실시간 폴링을 통합 관리합니다."
    )
    story.append(Paragraph(overview_text, body_style))
    story.append(Spacer(1, 10))

    # Section 2: Tree Structure
    story.append(Paragraph("2. 프론트엔드 코드 실행 트리 구조 (Architecture Tree)", h1_style))
    tree_text = """
<b>[App.jsx]</b> (최상위 루트 레이아웃 & 상태 통합 오케스트레이터)<br/>
│<br/>
├── <b>1. 훅(Hook) & 상태 초기화 레이어</b><br/>
│    ├── <b>useAuth()</b> : authMode ('main' | 'login' | 'signup' | 'dashboard'), authRole, currentUser 관리<br/>
│    ├── <b>useRouting()</b> : URL 경로 수신 및 상태 동기화 ('/', '/store-001.aicafe', '/kos', '/head-office')<br/>
│    ├── <b>useStorePolling()</b> : 5초 간격 실시간 API 폴링 (GET /api/stores/{storeId}/state, GET /eta)<br/>
│    └── <b>useChatbotSettings()</b> : 매장별 AI 챗봇 토글 상태 맵 관리<br/>
│<br/>
├── <b>2. 전역 헤더 & 프로필 모달 레이어</b><br/>
│    ├── <b>&lt;GnbHeader /&gt;</b> : 점주 및 매장 관리자용 상단 글로벌 헤더<br/>
│    ├── <b>&lt;HeadOfficeHeader /&gt;</b> : 본사 슈퍼바이저 전용 상단 헤더<br/>
│    └── <b>&lt;ProfileModal /&gt;</b> : 사용자 프로필 정보 및 로그아웃 팝업<br/>
│<br/>
└── <b>3. 화면 전환 & 렌더링 흐름 레이어</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;│<br/>
&nbsp;&nbsp;&nbsp;&nbsp;├── <b>[STEP 1] 메인 랜딩 페이지</b> (authMode === 'main')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│    └── <b>&lt;HeroSection /&gt;</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;│         ├── 브랜드 상단 헤더 (로고, 로그인/회원가입 버튼)<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│         ├── 실시간 AI 분석 카메라인식 비주얼 & 대기인원 모니터링<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│         └── 원클릭 빠른 체험 데모 버튼 ([본사 관리자], [동명점 점주], [수완점 점주])<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│<br/>
&nbsp;&nbsp;&nbsp;&nbsp;├── <b>[STEP 2] 인증 모달 레이어</b> (authMode === 'login' | 'signup')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│    └── <b>&lt;div className="auth-modal-overlay"&gt;</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;│         ├── <b>&lt;LoginPage /&gt;</b> : 역할 선택(점주/본사) & ID/PW 입력 ➔ handleLoginSuccess()<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│         └── <b>&lt;SignupPage /&gt;</b> : 역할 및 가맹점 선택 ➔ 회원가입 완료 후 로그인 이동<br/>
&nbsp;&nbsp;&nbsp;&nbsp;│<br/>
&nbsp;&nbsp;&nbsp;&nbsp;└── <b>[STEP 3] 대시보드 화면 전환 레이어</b> (authMode === 'dashboard')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── <b>&lt;section className="dashboard-content"&gt;</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├── <b>A. 매장 실시간 모니터링 대시보드</b> (page === 'store-001' | 'store-002')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│    └── <b>&lt;StoreDashboardView /&gt;</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── &lt;KpiSummaryBar /&gt; : 매장 총인원, 대기팀, ETA, 품절메뉴 요약<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── &lt;VisionMonitorPanel /&gt; : 카메라 실시간 감지 객체 Bounding Box<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── &lt;CameraSceneTwin /&gt; : 2D 디지틀 트윈 구역별 실시간 동선 지도<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         └── &lt;StoreChatbotWidget /&gt; : AI 매니저 챗봇 (POST ${AICC_BASE_URL}/chat)<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├── <b>B. KOS 매장 운영 & 정책 관리 화면</b> (page === 'kos')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│    └── <b>&lt;KosStoreManagementView /&gt;</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── &lt;RoleBanner /&gt; : 활성 매장 표시 및 매장 스위칭<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── &lt;MenuListPanel /&gt; : 메뉴 가격 및 품절 여부 토글 관리<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         └── &lt;PolicyListPanel /&gt; : 영업시간 및 운영 정책 설정<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├── <b>C. 본사 관제 & 통합 인사이트 화면</b> (page === 'head-office')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│    └── <b>&lt;SupervisorHeadOfficeView /&gt;</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── 가맹점 통합 집계 카드 (GET /api/stores/summary)<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         ├── AI 프랜차이즈 인사이트 (POST ${AICC_BASE_URL}/insights)<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│         └── &lt;OperationsSimulator /&gt; : 혼잡도 & 매출 시뮬레이터<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── <b>D. 시스템 설정 화면</b> (page === 'setting')<br/>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── <b>&lt;SettingsView /&gt;</b> (&lt;SceneEditor /&gt;, &lt;RoiEditor /&gt; 연동)
"""
    story.append(Paragraph(tree_text, code_style))
    story.append(Spacer(1, 10))

    # Section 3: Flow Details Table
    story.append(Paragraph("3. 단계별 화면 전환 & 코드 제어 흐름 명세", h1_style))
    
    data = [
        [Paragraph("<b>전환 단계</b>", body_style), Paragraph("<b>트리거 조건 / 핸들러</b>", body_style), Paragraph("<b>실행 코드 & 컴포넌트 렌더링</b>", body_style)],
        [
            Paragraph("<b>1. 메인 랜딩</b>", body_style),
            Paragraph("초기 접속<br/><code>authMode === 'main'</code>", body_style),
            Paragraph("<code>HeroSection.jsx</code> 렌더링.<br/>데모 버튼 클릭 시 <code>setAuthMode('login')</code> 호출", body_style)
        ],
        [
            Paragraph("<b>2. 로그인/가입</b>", body_style),
            Paragraph("로그인 버튼 클릭<br/><code>authMode === 'login'</code>", body_style),
            Paragraph("<code>LoginPage.jsx</code> 모달 팝업.<br/>성공 시 <code>handleLoginSuccess()</code> 실행", body_style)
        ],
        [
            Paragraph("<b>3. 매장 대시보드</b>", body_style),
            Paragraph("점주 로그인 완료<br/><code>page === 'store-001'</code>", body_style),
            Paragraph("<code>StoreDashboardView.jsx</code> 렌더링.<br/>5초 간격 API 폴링 & AI 챗봇 연결", body_style)
        ],
        [
            Paragraph("<b>4. KOS 운영 관리</b>", body_style),
            Paragraph("사이드바 메뉴 클릭<br/><code>page === 'kos'</code>", body_style),
            Paragraph("<code>KosStoreManagementView.jsx</code> 렌더링.<br/>메뉴/정책 API 조회 및 업데이트", body_style)
        ],
        [
            Paragraph("<b>5. 본사 통합 관제</b>", body_style),
            Paragraph("본사 관리자 로그인<br/><code>page === 'head-office'</code>", body_style),
            Paragraph("<code>SupervisorHeadOfficeView.jsx</code> 렌더링.<br/>전 가맹점 요약 및 AI 인사이트 리포트 생성", body_style)
        ]
    ]

    t = Table(data, colWidths=[90, 140, 257])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ECFDF5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#065F46')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    # Section 4: Summary Note
    summary_text = (
        "<b>📌 요약 및 특징:</b><br/>"
        "1. 본 아키텍처는 프론트엔드의 독립성을 보장하며 <code>.env</code>에 정의된 <code>VITE_API_BASE_URL</code> 및 <code>VITE_AICC_BASE_URL</code>을 중앙 수용합니다.<br/>"
        "2. 모든 대시보드는 <code>useStorePolling</code> 훅을 통해 실시간으로 8000번/8100번 백엔드와 연결됩니다."
    )
    story.append(Paragraph(summary_text, body_style))

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully created at: {pdf_path}")

if __name__ == "__main__":
    pdf_dest = "C:\\Users\\User\\.gemini\\antigravity\\brain\\e233f9c7-2e46-49d8-badd-189464a1af6e\\frontend_architecture_guide.pdf"
    build_pdf(pdf_dest)
