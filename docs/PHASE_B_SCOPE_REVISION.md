# Supported-scope revision — 10 October 2026

The user explicitly stopped further four-resistor dataset generation, ML
training and optimization development during Phase B. Active supported modes
are now up to two or up to three resistor modules PER front/tail branch.
Both include simpler networks. The 0.5 uF and 3 uF domains remain separate.

At the revision, all production dataset generation and all 32 candidate-model
training jobs had already finished. No four-resistor-specific process was
running. Those mixed one-through-four-module source/data/model artifacts remain
preserved as historical evidence; they must not be represented as newly trained
2/3-only artifacts. No further four-module acceptance campaign will run.
The active policy benchmark uses max_modules=2 and continues unchanged.

The existing predictors accept equivalent electrical parameters, not recipe
identity. Their applicability to supported two/three-module requests is assessed
separately; historical inclusion of four-module shapes is disclosed. Any future
training inputs must exclude four-module branches. Historical low-level
four-module arithmetic and artifacts remain available for reproduction, while
public application and command boundaries restrict supported requests to <=3.

A separate 5.6 Luna MAX agent owns the detailed-Physics two-versus-three
waveform comparison. It uses fixed per-case setups, identical objectives and
constraints, explicit search coverage, saved full waveforms, common-grid
metrics, a declared target-reference convention, and network-only controlled
comparisons. It trains no models and changes no validated Physics equations.

The waveform study and ongoing implementation run concurrently. Any policy
benchmark timing collected during that overlap is a shared-load observation,
not isolated-machine performance. An isolated follow-up timing sample is
required before making a quantitative speed claim. Original run evidence is
retained rather than overwritten.
