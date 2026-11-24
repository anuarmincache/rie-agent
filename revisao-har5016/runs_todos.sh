#!/bin/bash
cd /home/claude/work_base
mkdir -p /home/claude/out_abl
declare -A F=( [0.10]=Nd10_830 [0.15]=Nd15_850 [0.20]=Nd20_850 )
# B: original recipe (hand profile incl. Zero, X, Y held) + sample displacement refined
for x in 0.10 0.15 0.20; do
  RIE_SHIFT=1 python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_abl/B --label B_x$x --no-llm > /home/claude/out_abl/B_x$x.log 2>&1
done
# C: referee-1 protocol WITHOUT displacement (Zero=0, X=Y=0, size+microstrain, multistart)
for x in 0.10 0.15 0.20; do
  python tools/protocol_r1.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm /home/claude/out_abl/C C_x$x --nd $x --a-site nominal --size iso --uvw hold --multistart --no-disp 2>&1 | grep "^\[stage\]\|DONE\|Traceback\|Error" > /home/claude/out_abl/C_x$x.log
done
echo finished > /home/claude/out_abl/abl.done
#!/bin/bash
cd /home/claude/work_base
mkdir -p /home/claude/out_agent_r1
declare -A F=( [0.025]=Nd2p5_850 [0.05]=Nd5_870 [0.10]=Nd10_830 [0.15]=Nd15_850 [0.20]=Nd20_850 )
for x in ${@:-0.025 0.05 0.10 0.15 0.20}; do
  python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_agent_r1 --label r1_x$x --nd $x --no-llm --protocol r1 > /home/claude/out_agent_r1/log_x$x.txt 2>&1
done
echo finished > /home/claude/out_agent_r1/done_$$
#!/bin/bash
cd /home/claude/work_base
declare -A F=( [0.025]=Nd2p5_850 [0.05]=Nd5_870 [0.10]=Nd10_830 [0.15]=Nd15_850 [0.20]=Nd20_850 )
rm -rf /home/claude/out_agent_r1 /home/claude/out_leg2; mkdir -p /home/claude/out_agent_r1 /home/claude/out_leg2
for x in 0.025 0.05 0.10 0.15 0.20; do
  python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_agent_r1 --label r1_x$x --nd $x --no-llm --protocol r1 > /home/claude/out_agent_r1/log_x$x.txt 2>&1
done
for x in 0.10 0.15 0.20; do
  python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_leg2/legacy --label leg_x$x --no-llm > /home/claude/out_leg2/leg_x$x.log 2>&1
  RIE_SHIFT=1 python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_leg2/legshift --label legshift_x$x --no-llm > /home/claude/out_leg2/legshift_x$x.log 2>&1
done
echo finished > /home/claude/out_leg2/all.done
#!/bin/bash
cd /home/claude/work_base
declare -A F=( [Nd2p5]=Nd2p5_850 [Nd5]=Nd5_870 [Nd10]=Nd10_830 [Nd15]=Nd15_850 [Nd20]=Nd20_850 )
for k in Nd5 Nd10 Nd15 Nd20; do
  python src/agent.py data/samples/${F[$k]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_base_series --label base_${k} --no-llm > /home/claude/out_base_series/log_${k}.txt 2>&1
done
echo finished > /home/claude/out_base_series/base.done
#!/bin/bash
cd /home/claude/work_base
while [ ! -f /home/claude/out_leg2/all.done ]; do sleep 10; done
declare -A F=( [0.025]=Nd2p5_850 [0.05]=Nd5_870 [0.10]=Nd10_830 [0.15]=Nd15_850 [0.20]=Nd20_850 )
mkdir -p /home/claude/out_noshift /home/claude/out_leg2/legshift
for x in 0.10 0.15 0.20; do
  RIE_NO_SHIFT=1 python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_noshift --label noshift_x$x --nd $x --no-llm --protocol r1 > /home/claude/out_noshift/log_x$x.txt 2>&1
done
for x in 0.025 0.05; do
  RIE_SHIFT=1 python src/agent.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir /home/claude/out_leg2/legshift --label legshift_x$x --no-llm > /home/claude/out_leg2/legshift_x$x.log 2>&1
done
echo finished > /home/claude/out_noshift/done
#!/bin/bash
cd /home/claude/work_base
declare -A F=( [0.025]=Nd2p5_850 [0.05]=Nd5_870 [0.10]=Nd10_830 [0.15]=Nd15_850 [0.20]=Nd20_850 )
for x in 0.025 0.05 0.10 0.15 0.20; do for site in nominal pure; do
  python tools/protocol_r1.py data/samples/${F[$x]}.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm /home/claude/out_ms/${site} r1_x${x}_${site} --nd $x --a-site $site --size iso --uvw hold --multistart 2>&1 | grep "multistart\|^\[stage\]\|DONE\|Traceback\|Error" > /home/claude/out_ms/log_${x}_${site}.txt
done; done
echo finished > /home/claude/out_ms/series.done
#!/bin/bash
cd /home/claude/work_base
for size in iso axial; do for uvw in hold refine; do
  python tools/protocol_r1.py data/samples/Nd2p5_850.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm /home/claude/out_r1/var_${size}_${uvw} r1_nd25 --nd 0.025 --a-site pure --size $size --uvw $uvw 2>&1 | grep "^\[stage\]\|DONE\|Traceback\|Error" > /home/claude/out_r1/var_${size}_${uvw}.log
done; done
echo finished > /home/claude/out_r1/variants.done
