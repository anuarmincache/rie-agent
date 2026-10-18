# Setup Log

Chronological record of the development environment setup.
Platform: Windows 11 + WSL2 (Ubuntu 24.04), GitHub CLI, conda, GSAS-II from source.

## 1. Repository creation (2026-10-19)

    cd ~/projetos
    mkdir rie-agent && cd rie-agent
    git init -b main
    git add . && git commit -m "initial project structure"
    gh auth login
    gh repo create rie-agent --public --source=. --push

Remote: https://github.com/anuarmincache/rie-agent

### Issues encountered and fixes

| Issue | Cause | Fix |
|---|---|---|
| `fatal: detected dubious ownership` (GitHub Desktop) | Git for Windows does not trust WSL filesystem | `git config --global --add safe.directory '%(prefix)//wsl$/...'` |
| Path doubled (`rie-agent\rie-agent`) | Desktop appends repo name to path | point path at parent folder |
| GitHub Desktop unusable with WSL repos | recurring ownership issues | git + GitHub CLI inside WSL |
| `gh auth login` could not open browser | no xdg-open in WSL | device flow: github.com/login/device |

## 2. Conda environment (conda-forge only)

    conda config --set remote_read_timeout_secs 120
    conda create -n rie-agent --override-channels -c conda-forge \
      python=3.12 numpy=2.2 scipy pycifrw requests matplotlib pillow h5py pybaselines -y
    conda activate rie-agent

Python 3.12 + numpy 2.2 matches the prebuilt GSAS-II Linux binaries.

## 3. GSAS-II installation (from source + prebuilt binaries)

No `gsas2` conda package exists. Official route: git clone + binaries
from GSAS-II-buildtools releases.

    git config --global http.version HTTP/1.1
    git clone --depth 1 https://github.com/AdvancedPhotonSource/GSAS-II.git ~/GSAS-II

    mkdir -p ~/GSAS-II/GSASII-bin
    cd ~/GSAS-II/GSASII-bin
    curl -L --retry 5 -C - -o bins.tgz \
      https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/download/v1.0.1/linux_64_p3.12_n2.2.tgz
    tar xzf bins.tgz && rm bins.tgz

    cd ~/GSAS-II
    python -c "import GSASII.GSASIIscriptable as G2sc; G2sc.installScriptingShortcut()"

### Issues encountered and fixes

| Issue | Cause | Fix |
|---|---|---|
| conda-forge gsas2 not found | package does not exist | git clone (above) |
| `curl 92 HTTP/2 stream` during clone | unstable network | http.version HTTP/1.1 + --depth 1 |
| `ImportError: attempted relative import` | relative imports | run as module: `python -m GSASII.GSASIIscriptable` |
| `Unable to find GSAS-II binaries` | auto-download did not trigger | manual download into GSASII-bin/ |

## 4. Smoke test

    python -c "import G2script as G2sc; print(G2sc.ShowVersions())"

## 5. Agent dependencies

    pip install langgraph anthropic python-dotenv pytest pyyaml
    pip freeze > requirements.txt

## Tooling map

| Tool | Role |
|---|---|
| GitHub + GitHub CLI | version control, issues, releases, CI |
| Cursor (Windows + WSL) | main development IDE |
| Claude / ChatGPT / Kimi / Perplexity | architecture, review, literature |
| GSAS

cat > docs/ROADMAP.md << 'EOF'
# Roadmap

Development plan for rie-agent, organized in sprints.
Golden rule: **deterministic pipeline first, LLM agent last**.

## Sprint 0 - Headless staged refinement (no AI)  <- CURRENT

Scripted Rietveld refinement via GSASIIscriptable:
- Input: diffraction data (.xye/.gss), phase .cif, instrument .instprm
- Classic staged recipe: scale -> background -> lattice -> profile ->
  atomic positions -> thermal parameters
- Log Rwp, GOF and key parameters after every stage
- Target sample: Nd-doped BiFeO3 (lab XRD first, neutrons later)

Done when: one command refines a sample end-to-end and writes a
stage-by-stage quality report.

## Sprint 1 - Deterministic validators

Pure functions: refinement state -> OK/FAIL + reason.
- Rwp/GOF thresholds and trend (worsening = fail)
- Biso within physically reasonable range
- Occupancies within [0, 1]
- Divergence detection (covariance, parameter shifts vs esd)
- Phase-specific checks (Bi-Fe-O secondary phases: Bi25FeO40, Bi2Fe4O9)

## Sprint 2 - LLM agent

Orchestrator (LangGraph) deciding the next stage given state + trajectory,
with automatic rollback on validator failure. LLM for diagnosis/planning
only - never for numeric decisions. Local models via Ollama by default
(open source); paid API as an optional user-configured backend.

## Sprint 3 - Benchmarks

- Full battery on Bi1-xNdxFeO3 series (multiple x)
- Public reference datasets
- Comparison against manual expert refinement (baseline)

## Sprint 4 - Visualization module (Blender)

render_structure.py: refined CIF -> publication-quality PNG/animation
via Blender bpy. Antiferromagnetic spin-cycloid visualization for BiFeO3.

## Sprint 5 - JOSS paper + v1.0 release

- paper/joss/paper.md + paper.bib
- GitHub release v1.0, Zenodo DOI, CITATION.cff
- CI: automated refinement smoke test + PDF builds

## Sprint 6 - Full article (J. Appl. Cryst. or Powder Diffraction)

Complete science paper in LaTeX (paper/jac/, IUCr template):
agent architecture, validation framework, BiFeO3:Nd case study.
Figures generated programmatically (matplotlib + Blender renders).
