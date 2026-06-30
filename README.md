# 메모리 뚱냥이 🐱 (Memory Tubby Cat)

A tiny desktop cat that gets chubbier as your disk fills up.  
디스크 용량이 찰수록 점점 통통해지는 데스크톱 고양이 위젯입니다.

Think RunCat, but for disk usage.  
The fatter the cat, the fuller your drive.

메모리 뚱냥이는 바탕화면 위에 둥둥 떠 있는 작은 고양이입니다.  
디스크가 여유로우면 작은 애기냥, 디스크가 거의 꽉 차면 빵빵한 돼지냥이 됩니다.

macOS와 Windows를 지원합니다.
이미지 커스텀이 가능합니다. 

## Screenshots

<table>
  <tr>
    <td align="center">
      <img src="./cute.png" width="260"><br>
      <sub>디스크가 꽉 차면 통통해지는 기본 냥이</sub>
    </td>
    <td align="center">
      <img src="./simple.png" width="260"><br>
      <sub>테마별로 다른 뚱냥이</sub>
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <img src="./context-menu.png" width="400"><br>
      <sub>우클릭으로 디스크, RAM, 메모리 많이 쓰는 앱, 테마와 크기를 확인할 수 있습니다</sub>
    </td>
  </tr>
</table>


## 만든 이유

요즘 Claude Code와 Hermes 같은 AI 도구를 열심히 써보다 보니, 어느 순간 디스크 용량이 생각보다 빨리 줄어드는 걸 느꼈습니다.

가상환경, 패키지, 캐시, 데스크톱 앱 파일들이 조용히 쌓이더라고요.

디스크 용량 경고는 유용하지만 별로 귀엽지는 않았고, 디스크가 찰수록 고양이가 같이 통통해지면 재밌기도 하고 눈으로 확인하기에도 좋겠다고 생각했습니다.
특히, 이 위젯을 만드는데 아이디어를 준 친구가 고양이를 좋아하거든요. 

그래서 만든 작은 시스템 모니터이자 데스크톱 펫입니다.


## Features

- 디스크 사용량에 따라 고양이가 애기냥 → 통통냥 → 돼지냥으로 변합니다
- RAM 사용량도 함께 볼 수 있습니다
- 메모리 많이 쓰는 앱을 확인할 수 있습니다
- 바탕화면 위에 둥둥 떠 있고, 드래그로 위치를 옮길 수 있습니다
- 우클릭으로 상세 사용량, 메모리 많이 쓰는 앱, 테마, 크기를 확인하고 바꿀 수 있습니다
- 이미지 한 장으로 나만의 테마를 추가할 수 있습니다
- 설정을 자동 저장합니다
- 로그인 시 자동 실행할 수 있습니다
- macOS와 Windows를 지원합니다

## Themes

기본 테마는 귀여운 것부터 약간 이상한 것까지 4종을 제공합니다.

| 테마 | 설명 |
|---|---|
| 귀여운 | 3D 토이 느낌의 뚱냥이. 뚱뚱할수록 눈이 게슴츠레해집니다 |
| 단순한 | 심플한 일러스트 스타일의 뚱냥이 |
| 광기 | 큰 반짝이 눈을 가진 치비냥. 약간 이상하지만 귀엽습니다 |
| 경각심 | 금방이라도 쓰러질것같은 지친냥. 이름처럼 경각심을 줍니다 |


---

## Installation — macOS
```bash
git clone https://github.com/hyeonheebee/memory-cat.git
cd memory-cat
./install_mac.command        
```
`install_mac.command`는 더블클릭해서 실행해도 됩니다.
Python 3.9 이상이 설치되어 있으면, 가상환경을 만들고 필요한 의존성을 설치한 뒤 앱을 실행합니다.

삭제하려면 아래 명령어를 실행하세요.
```bash
./uninstall_mac.command
```
---

## Installation — Windows

Windows에서는 `windows/` 폴더의 `README.txt`를 참고해주세요.
간단히 실행하려면:
```bat
git clone https://github.com/hyeonheebee/memory-cat.git
cd memory-cat
pip install pyside6 psutil
pythonw windows\windows_cat.pyw
```

Python 없이 `.exe`로 사용하고 싶다면:
```bat
`windows\build_exe.bat`
```
로 `.exe`를 만들 수 있어요.


---

## 나만의 테마 만들기 🎨

가로로 N단계가 나열된 고양이 이미지 한 장만 있으면 나만의 테마를 만들 수 있습니다.
예를 들면 이런 이미지입니다.

> 같은 고양이가 6단계로 점점 통통해지는 이미지  
> 흰 배경  
> 한 줄로 나열된 형태

ChatGPT나 이미지 생성 도구로 이런 식의 이미지를 만든 뒤 사용할 수 있습니다.

[1] 개발용 의존성을 먼저 설치합니다.
```bash
# (가상환경 기준) 이미지 변환 도구 의존성
./.venv/bin/python -m pip install -r requirements-dev.txt
```

[2]이미지를 테마로 변환합니다.
```bash
# 이미지 -> 테마 (흰 배경 자동 제거 + 정렬 + 단계화)
./.venv/bin/python import_theme.py 내고양이.png 내테마이름
```

앱을 다시 실행하면 우클릭 테마 메뉴에 `내 테마이름`이 자동으로 나타납니다.
테마는 아래 폴더를 자동으로 인식합니다
```bash
frames/<테마이름>/
```

코드로 그리는 기본 테마 프레임은 아래 명령어로 다시 만들 수 있습니다.
```bash
python generate_frames.py
```
---

## Project structure
```
desktop_cat.py       macOS app, built with PyObjC
windows/             Windows app, built with PySide6
metrics.py           shared disk and memory metrics
generate_frames.py   generates built-in theme frames
import_theme.py      converts an image into a custom theme
frames/<theme>/      PNG frames for each theme
```

## Notes
이 프로젝트는 재미로 시작한 작은 데스크톱 위젯입니다.

설치 환경에 따라 예상하지 못한 이슈가 있을 수 있습니다.  
써보다가 고양이가 이상하게 굴거나, 너무 빨리 살찌거나, 실행이 잘 안 되면 이슈로 알려주세요. 
[피드백 제보 링크](https://forms.gle/yeboaGjzpfzaqWAJA)

## 만든이 / License

심현희 ([@hyeonheebee](https://github.com/hyeonheebee)) + Claude 🐾 · [MIT](LICENSE)
