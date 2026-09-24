"""PySide6 대화상자. **판단은 하지 않는다** — win_ai 가 정한 것을 띄우기만.

맥 개발 환경에는 PySide6 가 없어 이 파일은 테스트가 안 돈다. 그래서 조건문을
여기 두면 아무도 검사하지 못한다. 새 규칙이 생기면 win_ai 에 넣는다.

스레드 규칙 두 가지:

* 워커의 ``run()`` 안에서는 Qt 위젯을 절대 만지지 않는다. 결과는 시그널로만
  내보낸다.
* 워커 시그널을 lambda·일반 함수에 이을 때는 ``QueuedConnection`` 을 명시한다.
  그래야 메시지 상자가 반드시 GUI 스레드에서 뜬다. 자동 연결에 맡기면 받는 쪽이
  QObject 가 아닐 때 PySide6 버전에 따라 워커 스레드에서 바로 불릴 수 있다.
"""

from PySide6 import QtCore, QtWidgets

import win_ai
from i18n import tr

#: 파일 고르기 창의 형식 필터. 사용자에게 보이는 문장이 아니라 Qt 문법이다.
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"


def _queued():
    return QtCore.Qt.ConnectionType.QueuedConnection


def _explain_missing_key(parent, language):
    title, body = win_ai.api_key_missing_message(language)
    QtWidgets.QMessageBox.information(parent, title, body)


def _bring_to_front(box):
    """대화상자가 다른 창 뒤에 숨지 않도록 항상 위로 끌어온다.

    고양이 창은 ``FramelessWindowHint | WindowStaysOnTopHint | Tool``
    이다(``windows_cat.pyw``). 윈도우에서 ``Tool`` 창의 자식 대화상자는 그
    항상-위를 물려받지 못해 다른 창 뒤에서 열릴 수 있다 — 대화상자
    자신에게도 항상-위 플래그를 직접 준다.

    순서 근거(Qt 문서, PySide6 도 같은 C++ API 를 그대로 감싼다):

    * ``setWindowFlag()``/``setWindowFlags()`` 는 최상위 창을 다시 만들며
      (내부적으로 ``setParent()`` 를 부른다) 그 창을 **숨긴다** — 문서가
      "You must call show() to make the widget visible again" 라고
      경고한다. 그래서 **아직 한 번도 보이지 않은 시점**(``box.exec()`` 를
      부르기 전)에 플래그를 준다 — 숨었다 다시 뜨는 깜빡임이 없다.
    * ``activateWindow()`` 는 창이 이미 보이는 상태가 아니면 아무 효과가
      없다 — 문서: "Note that the window must be visible, otherwise
      activateWindow() has no effect." 그래서 ``show()`` **뒤에** 부른다.
    * 같은 문서가 쌓임 순서까지 확실히 하려면 ``raise_()`` 도 같이 부르라고
      되어 있다("If you want to ensure that the window is stacked on top
      as well you should also call raise_()") — 그래서 ``raise_()`` 를
      ``activateWindow()`` 바로 앞에 둔다.
    * 뒤이어 부르는 ``box.exec()`` 는 이미 보이는 창을 다시 숨겼다 띄우지
      않는다 — ``QDialog.exec()`` 문서는 "always pops up the dialog as
      modal"(modal 프로퍼티 값과 무관하게 언제나 모달로 띄운다)이라고만
      말할 뿐, 창 플래그(항상-위 등)에 대해서는 아무 조건을 걸지 않는다.
      즉 여기서 준 ``WindowStaysOnTopHint`` 는 ``exec()`` 의 모달성과
      서로 다른 축(플래그 vs 모달리티)이라 충돌하지 않고, 모달 동작은
      그대로 유지된다.
    """
    box.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
    box.show()
    box.raise_()
    box.activateWindow()


class _DiagnosisWorker(QtCore.QThread):
    """``brain.diagnose`` 는 OpenAI 타임아웃 20초·재시도 1회라 수십 초 걸릴 수
    있다. UI 스레드에서 부르면 그동안 고양이가 얼어붙는다."""

    finished_ok = QtCore.Signal(object)     # 줄 목록(list[str])
    failed = QtCore.Signal(str)

    def __init__(self, language):
        super().__init__()
        self._language = language

    def run(self):
        try:
            lines = win_ai.diagnosis_lines(self._language)
        except Exception as error:
            # 원문은 로그로만 보낸다 — 로그 함수 자체는 예외를 내지 않으므로
            # 워커 스레드에서 새 예외가 생길 걱정은 없다. 시그널에도 원문
            # 대신 번역된 안내만 실어 보낸다(R26) — 받는 쪽이 실수로 원문을
            # 그대로 띄우는 일이 없도록 애초에 안전한 문자열만 내보낸다.
            win_ai.log_ai_failure("diagnosis", error)
            self.failed.emit(tr(self._language, "diagnosis_error"))
            return
        self.finished_ok.emit(lines)


class _ThemeWorker(QtCore.QThread):
    """생성은 1~2 분 걸린다. UI 스레드에서 돌리면 앱이 얼어붙는다."""

    finished_ok = QtCore.Signal(str)        # 만든 테마 이름
    failed = QtCore.Signal(str)

    def __init__(self, photo, name, language):
        super().__init__()
        self._photo, self._name, self._language = photo, name, language

    def run(self):
        try:
            name = win_ai.create_theme(self._photo, self._name, self._language)
        except Exception as error:
            # create_theme 이 내는 ThemeError 는 이미 번역된 메시지다. 그 밖의
            # (있어선 안 되는) 예외가 새 나오면 원문 대신 일반 안내로 감춘다
            # — 판단은 win_ai.theme_failure_message 가, 여기서는 결과만 emit.
            if not isinstance(error, win_ai.ThemeError):
                win_ai.log_ai_failure("theme", error)
            self.failed.emit(win_ai.theme_failure_message(error, self._language))
            return
        self.finished_ok.emit(name)


def _show_diagnosis(parent, language, lines):
    QtWidgets.QMessageBox.information(
        parent, tr(language, "diagnosis_title"), "\n".join(lines))


def _show_diagnosis_failure(parent, language, message):
    # message 는 워커가 이미 번역해서 emit 한 안내 문구다(원문은 로그로만
    # 간다) — 여기서 다시 tr() 을 불러 따로 만들지 않고 그대로 띄운다.
    QtWidgets.QMessageBox.warning(
        parent, tr(language, "diagnosis_title"), message)


def show_diagnosis(parent, language):
    """진단을 워커 스레드에서 시작하고 워커를 돌려준다. 키가 없으면 ``None``.

    호출부는 돌려받은 워커를 붙잡고 있어야 한다. 지역 변수로 두면 GC 가 도는
    스레드를 거둬 가서 앱이 죽는다.
    """
    if not win_ai.has_api_key():
        _explain_missing_key(parent, language)
        return None

    worker = _DiagnosisWorker(language)
    worker.finished_ok.connect(
        lambda lines: _show_diagnosis(parent, language, lines), _queued())
    worker.failed.connect(
        lambda message: _show_diagnosis_failure(parent, language, message),
        _queued())
    worker.start()
    return worker


def _show_theme_failure(parent, language, message):
    QtWidgets.QMessageBox.warning(
        parent, tr(language, "pet_theme_error_title"), message)


def make_theme(parent, language, bundled_frames_dir, on_done):
    """사진을 골라 테마 생성을 워커 스레드에서 시작하고 워커를 돌려준다.

    중간에 그만두면(키 없음·취소·형식 오류·동의 안 함) ``None``.
    ``on_done(name)`` 은 GUI 스레드에서 불린다.
    """
    if not win_ai.has_api_key():
        _explain_missing_key(parent, language)
        return None

    photo, _ = QtWidgets.QFileDialog.getOpenFileName(
        parent, tr(language, "menu_pet_theme"), "", IMAGE_FILTER)
    if not photo:
        return None

    problem = win_ai.check_photo(photo, language)
    if problem:
        QtWidgets.QMessageBox.warning(parent, tr(language, "menu_pet_theme"), problem)
        return None

    # QMessageBox.question 의 기본 Yes/No 는 버튼이 영어이고 기본 버튼이
    # Yes 라 엔터 한 번에 사진이 전송된다. 직접 만들어 한국어 버튼을 달고
    # 기본·Esc 버튼을 모두 "취소"로 둔다.
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    box.setWindowTitle(tr(language, "pet_theme_consent_title"))
    box.setText(tr(language, "pet_theme_consent_body"))
    continue_label, cancel_label = win_ai.consent_button_labels(language)
    continue_button = box.addButton(
        continue_label, QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    cancel_button = box.addButton(
        cancel_label, QtWidgets.QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.setEscapeButton(cancel_button)

    # K-1: 무효 키로도 동의창이 안 보였다는 실기 보고가 있었다 — 코드로는
    # 원인이 밝혀지지 않아(추정하지 않는다) 유일한 코드 근거인 이 지점만
    # 고친다. 동의 3지점(shown·accepted·declined)도 같은 로그에 남겨 다음
    # 실기에서 기록으로 판정한다.
    win_ai.log_consent("shown")
    _bring_to_front(box)
    box.exec()
    if box.clickedButton() is continue_button:
        win_ai.log_consent("accepted")
    else:
        win_ai.log_consent("declined")
        return None

    # 기본 테마·이미 만든 테마와 겹치지 않는 이름(mypet, mypet2, ...).
    # vision_theme 은 있는 폴더를 덮어쓰지 않으므로 고정 이름을 쓰면 두 번째부터 실패한다.
    name = win_ai.next_theme_name(bundled_frames_dir)

    # 안내창은 모달이라 사용자가 닫을 때까지 여기서 멈춘다. 스레드를 시작하기
    # **전에** 띄운다 — 시작한 뒤에 띄우면 이 창에서 예외가 났을 때 도는 워커를
    # 아무도 붙잡지 않은 채 GC 에 넘기게 된다.
    QtWidgets.QMessageBox.information(
        parent, tr(language, "menu_pet_theme"), tr(language, "theme_working"))

    worker = _ThemeWorker(photo, name, language)
    worker.finished_ok.connect(on_done, _queued())
    worker.failed.connect(
        lambda message: _show_theme_failure(parent, language, message), _queued())
    worker.start()
    return worker          # 참조를 잡아 두지 않으면 GC 가 스레드를 죽인다
