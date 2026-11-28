# Original cheerful instrumental (synthesized, royalty-free: we made it ourselves).
import numpy as np, wave, sys
SR=44100; BPM=112; beat=60/BPM; total=125
n=int(SR*total); out=np.zeros(n)
def note(f,t0,dur,amp=0.3,kind="bell"):
    s=int(t0*SR); l=int(dur*SR)
    if s>=n: return
    l=min(l,n-s); t=np.arange(l)/SR
    if kind=="bell":
        w=np.sin(2*np.pi*f*t)+0.4*np.sin(2*np.pi*2*f*t)+0.15*np.sin(2*np.pi*3*f*t)
        env=np.exp(-t*5.5)
    else:
        w=np.sin(2*np.pi*f*t)+0.2*np.sin(2*np.pi*2*f*t); env=np.exp(-t*3)
    a=int(0.005*SR); env[:a]*=np.linspace(0,1,a)
    out[s:s+l]+=amp*w*env
C=261.63
sc=[C*2**(k/12) for k in (0,2,4,7,9,12,14,16,19)]  # C major pentatonic (+octave)
mel_a=[4,4,5,4,2,2,3,2, 0,1,2,3,4,4,4,4]   # indexes, 8th notes
mel_b=[5,5,6,5,4,4,3,2, 3,4,3,2,1,1,0,0]
bass=[C/2,C/2*1.3348,C/2*1.4983,C/2*1.3348]  # C F G F-ish
chords=[(0,4,7),(5,9,12),(7,11,14),(5,9,12)]
bar=4*beat; nb=int(total/bar)
for b in range(nb):
    t0=b*bar
    bf=bass[b%4]; 
    for k in range(4): note(bf,t0+k*beat,beat*0.9,0.22,"bass")
    for d in chords[b%4]:
        f=C*2**((d)/12)
        for k in (0.5,1.5,2.5,3.5): note(f,t0+k*beat,beat*0.4,0.06,"bell")
    seq=mel_a if (b//2)%2==0 else mel_b
    half=(b%2)*8
    for k in range(8):
        idx=seq[half+k] if half+k<len(seq) else seq[k]
        note(sc[idx],t0+k*beat/2,beat*0.45,0.17,"bell")
out/= max(1e-9,np.max(np.abs(out)))/0.8
fade=int(2*SR); out[-fade:]*=np.linspace(1,0,fade)
pcm=(out*32767).astype(np.int16)
with wave.open(sys.argv[1],"w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
