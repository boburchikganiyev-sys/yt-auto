"""Rainbow Friends: clips + English kid voice (edge-tts) + music + subtitles -> out/rainbow_friends.mp4"""
import asyncio, os, subprocess, sys, textwrap
D=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(D,"out"); TMP=os.path.join(D,"tmp")
os.makedirs(OUT,exist_ok=True); os.makedirs(TMP,exist_ok=True)
VOICE=os.environ.get("VOICE","en-US-AnaNeural")
LINES=[
"Hello, hello! I am Mimo! Let's sing and play with colors!",
"Colors, colors, all around! Rainbow friends are in our town!",
"I am Mimo, red like a rose! Red is my scarf, and red is my nose!",
"Wiggle, wiggle, wiggle my toes! Hello, friends, here we go!",
"Lulu the duck is yellow like the sun! Splash in the puddle, it's so much fun!",
"Quack, quack, quack, and waddle along! Yellow, yellow, sing the song!",
"Clap, clap, clap, and dance with me! What do you see? What do you see?",
"Bobo is blue like the big wide sea! Squirt, squirt, squirt with his trunk! Whee!",
"Stomp, stomp, stomp, so big and strong! Blue, blue, sing along!",
"Kiki is pink like cotton candy! Hop, hop, hop, she's quick and handy!",
"Twitch her nose, and wiggle her ears! Pink, pink, give three cheers!",
"Colors, colors, all around! Rainbow friends are in our town!",
"Clap, clap, clap, and dance with me! Red, yellow, blue, and pink! Hooray!",
"Bye-bye, bye-bye, see you soon! Wave to the sun, and wave to the moon!",
"Goodnight, rainbow friends. Sweet dreams!",
]
def run(c):
    r=subprocess.run(c,capture_output=True,text=True)
    if r.returncode: print("CMD FAILED:"," ".join(c)[:400]); print(r.stderr[-1500:]); sys.exit(1)
    return r.stdout
def dur(p): return float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]).strip())
async def tts(text,path):
    import edge_tts
    try:
        await edge_tts.Communicate(text,VOICE,rate="-4%",pitch="+8Hz").save(path)
    except Exception as e:
        print("TTS retry without pitch:",repr(e))
        await edge_tts.Communicate(text,VOICE,rate="-4%").save(path)
def main():
    segs=[]
    for i,line in enumerate(LINES,1):
        n=f"{i:02d}"; clip=os.path.join(D,"clips",f"{n}.mp4")
        mp3=os.path.join(TMP,f"v{n}.mp3"); seg=os.path.join(TMP,f"s{n}.mp4")
        if os.environ.get("NO_TTS"):
            run(["ffmpeg","-v","error","-y","-f","lavfi","-i","anullsrc=r=44100:cl=mono","-t","6",mp3])
        else:
            asyncio.run(tts(line,mp3))
        d=dur(mp3); tempo=1.0
        if d>7.0: tempo=min(1.5,d/7.0)   # fit into the 8 s clip
        txt=os.path.join(TMP,f"t{n}.txt"); open(txt,"w").write("\n".join(textwrap.wrap(line,42)))
        font="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        vf=(f"scale=1280:720,fps=24,drawtext=fontfile={font}:textfile={txt}:fontsize=40:fontcolor=white:"
            f"borderw=4:bordercolor=black@0.8:x=(w-text_w)/2:y=h-text_h-40:line_spacing=8,format=yuv420p")
        # voice starts at 0.4s; original clip audio ducked; music added later globally
        af=(f"[1:a]atempo={tempo},adelay=400|400,volume=1.6[v];[0:a]volume=0.25[o];"
            f"[o][v]amix=inputs=2:duration=first:normalize=0,apad,atrim=0:8,asetpts=N/SR/TB[a]")
        run(["ffmpeg","-v","error","-y","-i",clip,"-i",mp3,"-filter_complex",af,"-vf",vf,"-map","0:v","-map","[a]","-t","8",
             "-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-ar","44100","-ac","2",seg])
        segs.append(seg); print("ok",n,round(d,1),"s voice")
    lst=os.path.join(TMP,"list.txt"); open(lst,"w").write("".join(f"file '{s}'\n" for s in segs))
    joined=os.path.join(TMP,"joined.mp4")
    run(["ffmpeg","-v","error","-y","-f","concat","-safe","0","-i",lst,"-c","copy",joined])
    final=os.path.join(OUT,"rainbow_friends.mp4")
    run(["ffmpeg","-v","error","-y","-i",joined,"-stream_loop","-1","-i",os.path.join(D,"music.mp3"),
         "-filter_complex","[1:a]volume=0.30[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
         "-map","0:v","-map","[a]","-c:v","copy","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",final])
    print("DONE",final,round(dur(final),1),"s")
main()
