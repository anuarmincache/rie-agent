"""Convert Rigaku ASCII dump (.txt) to GSAS-II .xye (2theta, I, esd)."""
import sys
import numpy as np

def convert(inp, out, header_lines=31):
    d = np.loadtxt(inp, skiprows=header_lines)
    tt, i = d[:, 0], d[:, 1]
    esd = np.sqrt(np.maximum(i, 1))
    with open(out, "w") as f:
        f.write("# converted from Rigaku ASCII dump\n# 2theta  I  esd\n")
        for x, y, s in zip(tt, i, esd):
            f.write(f"{x:.4f}  {y:.1f}  {s:.2f}\n")
    print(f"{inp} -> {out} ({len(tt)} points)")

if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
