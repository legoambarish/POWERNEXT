from .network import Element,Network

def uniform_stage_chain(n,cs,rf,rt,load_c,loop_l,stage_charge,parallel_tail=None):
    """Synthetic uniform slice-chain: proof fixture, NOT a CPRI erected schematic.

    Each charged capacitor has a local parallel tail resistor. Front resistors
    are interleaved between slices; the final front resistor is in series with L.
    No intermediate-to-earth capacitance is included, so symmetry permits an
    exact reduced GSHUNT representation. Ground capacitance would break it.
    """
    nodes=[]; elements=[]; init={}
    for k in range(1,n+1):
        a=f"a{k}"; b="0" if k==1 else f"b{k}"
        if k>1:
            nodes.append(b); init[b]=(k-1)*stage_charge
            elements.append(Element(f"Rf{k-1}","R",f"a{k-1}",b,rf))
        nodes.append(a); init[a]=k*stage_charge
        elements.extend([Element(f"Cs{k}","C",a,b,cs),Element(f"Rt{k}","R",a,b,rt)])
        if parallel_tail is not None:
            elements.append(Element(f"Rt_parallel{k}","R",a,b,parallel_tail))
    nodes.append("o"); init["o"]=0.0
    elements.append(Element("CL","C","o","0",load_c))
    if loop_l>0: elements.append(Element(f"Rf{n}L","RL",f"a{n}","o",loop_l,rf))
    else: elements.append(Element(f"Rf{n}","R",f"a{n}","o",rf))
    return Network(nodes,elements).compile(init)
