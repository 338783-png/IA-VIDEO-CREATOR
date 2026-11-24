"""Génère une vidéo de référence synthétique dont les caractéristiques sont connues (vérité terrain).

Plans (30 fps, 1080x1920) :
  1  0.0-2.0  mire SMPTE fixe                coupe à 2.0
  2  2.0-3.5  aplat orange fixe              coupe à 3.5
  3  3.5-6.0  zoom avant 1.0 -> ~1.35        coupe à 6.0
  4  6.0-7.0  aplat bleu                     fondu enchaîné 0.5 s centré sur 7.0
  5  7.0-9.0  mire animée (testsrc2)         fondu au noir centré sur 9.0
  6  9.0-12.0 panoramique horizontal
Sous-titres : un mot toutes les 0.5 s, blanc contour noir, en bas.
Audio : pulsation 120 BPM (temps toutes les 0.5 s) + nappe -> coupes franches sur les temps.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

WORDS = "Voici une vidéo test pour vérifier que lanalyse détecte bien chaque élément du style comme prévu ici".split()


def ass_time(t: float) -> str:
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def make(out: Path) -> Path:
    tmp = Path(tempfile.mkdtemp())
    ass = tmp / "subs.ass"
    lines = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             "Style: Default,DejaVu Sans,110,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,7,0,2,60,60,380,1", "",
             "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i, w in enumerate(WORDS[:24]):
        lines.append(f"Dialogue: 0,{ass_time(i * 0.5)},{ass_time(i * 0.5 + 0.5)},Default,,0,0,0,,{w.upper()}")
    ass.write_text("\n".join(lines), encoding="utf-8")

    S = "1080x1920"
    fc = (
        f"smptehdbars=s={S}:r=30:d=2[s1];"
        f"color=c=0xFF7A00:s={S}:r=30:d=1.5[s2];"
        f"testsrc=s=1080x1920:r=30:d=1,trim=end_frame=1,loop=loop=75:size=1:start=0,setpts=N/30/TB,"
        f"zoompan=z='1+0.0045*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={S}:fps=30[s3];"
        f"color=c=0x1E5AFF:s={S}:r=30:d=1.25[s4];"
        f"testsrc2=s={S}:r=30:d=2.25,fade=t=out:st=2.0:d=0.25[s5];"
        f"testsrc=s=3240x1920:r=30:d=1,trim=end_frame=1,loop=loop=90:size=1:start=0,setpts=N/30/TB,"
        f"crop=1080:1920:x='n*20':y=0,fade=t=in:st=0:d=0.25[s6];"
        f"[s4][s5]xfade=transition=fade:duration=0.5:offset=0.75[s45];"
        f"[s1][s2][s3][s45][s6]concat=n=5:v=1:a=0,fps=30,format=yuv420p,subtitles='{ass}'[v];"
        f"aevalsrc='0.7*sin(2*PI*55*t)*exp(-25*mod(t,0.5))+0.08*sin(2*PI*220*t)':s=44100:d=12[a]"
    )
    cmd = ["ffmpeg", "-y", "-v", "error", "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-t", "12", str(out)]
    subprocess.run(cmd, check=True)
    return out


GROUND_TRUTH = {
    "boundaries": [2.0, 3.5, 6.0, 7.0, 9.0],
    "types": ["cut", "cut", "cut", "crossfade", "fade_black"],
    "zoom_scene": 3, "pan_scene": 6, "bpm": 120,
}

if __name__ == "__main__":
    print(make(Path(sys.argv[1] if len(sys.argv) > 1 else "reference_test.mp4")))
