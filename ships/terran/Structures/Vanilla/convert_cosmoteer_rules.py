
#!/usr/bin/env python3
"""
Cosmoteer structure converter -> exact target format (per user's example).

- Keeps: ID, AllowedContiguity (if present), IsRotateable (true if present or default true)
- Sets inheritance to <../base_part_terran_structure.rules>/Part
- Rewrites NameKey/IconNameKey to "Parts/EXPV<Structure...>" (underscore-stripped, capitalized fragment)
- Writes standardized top-level blocks/keys, including:
    Resources, MaxHealth, InitialPenetrationResistance, Density, CellOccupancyFactor
    GenerateRectCollider=false
    EditorIcon {...} (icon.png, Size [32,32], SampleMode Linear)
- Preserves CustomCollider vertices -> emitted as Components/Collider { Type=PolygonCollider; Vertices[...] }
- Components structure exactly as requested:
    Components : ^/0/Components
    {
        Collider {...}             # from old CustomCollider or similar
        ConstructionEffects : ^/0/ConstructionEffects { AtlasSprite... }
        Graphics { Floor { Layer="structure"; DamageLevels [ structure.png / normals ] } }
        DestroyedEffects { ... }
        Blueprints { ... }
    }
- Appends Scale = (<inferred>)

Output file: "<samefolder>/<stem>_converted.rules"

Usage (PowerShell):  python .\convert_cosmoteer_rules.py "D:\path\to\folder"
"""

import argparse
import re
from pathlib import Path

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")

def find_top_assign(text: str, key: str):
    m = re.search(rf'(?im)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(.+)$', text)
    if m:
        val = m.group(1).strip()
        val = re.sub(r'//.*$', '', val).strip()
        return val
    return None

def extract_block(text: str, block_name: str):
    # Extract balanced {...} block
    pat = re.compile(rf'(?im)^([ \t]*{re.escape(block_name)}[ \t]*\{{)')
    m = pat.search(text)
    if not m:
        return None, None
    start = m.start(1)
    i = m.end(1) - 1
    depth = 0
    end = None
    for j in range(i, len(text)):
        c = text[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        end = len(text)
    full = text[start:end]
    inner = full[full.find('{')+1:end-start-1]
    return full, inner

def extract_all_customcollider_vertices(text: str):
    """Find CustomCollider arrays in either {...} or [...] form and parse vertices [[x,y] ...]."""
    verts_sets = []
    # Match either "CustomCollider { ... }" or "CustomCollider [ ... ]"
    pat = re.compile(r'(?ims)^\s*CustomCollider\s*([\{\[])(.*?)[\}\]]', re.M | re.S)
    for m in pat.finditer(text):
        inner = m.group(2)
        pts = re.findall(r'\[\s*([0-9]*\.?[0-9]+)\s*,\s*([0-9]*\.?[0-9]+)\s*\]', inner)
        if pts:
            verts = [[float(a), float(b)] for a,b in pts]
            verts_sets.append(verts)
    return verts_sets

def pascalize_namekey_fragment(old_name: str) -> str:
    q = old_name.strip().strip('"')
    if q.lower().startswith("parts/"):
        frag = q[6:]
    else:
        frag = q
    frag = frag.replace("_", "")
    return f'Parts/EXPV{frag}'

def name_to_icon(namekey: str) -> str:
    return f'{namekey}Icon'

def infer_scale_from_filename(filename: str) -> float | None:
    low = filename.lower()
    if "1quarter" in low:
        return 0.25
    if "2quarter" in low:
        return 0.5
    if "3quarter" in low:
        return 0.75
    return None

def infer_scale(old_text: str, fallback_name: str) -> float:
    s = infer_scale_from_filename(fallback_name)
    if s is not None:
        return s
    mh = find_top_assign(old_text, "MaxHealth")
    if mh:
        m = re.search(r'(\d+)', mh)
        if m:
            val = int(m.group(1))
            if val % 250 == 0:
                return round(val / 1000.0, 2)
    return 1.0

def format_allowed_contiguity(old_text: str) -> str:
    ac = find_top_assign(old_text, "AllowedContiguity")
    if ac:
        return ac if ac.strip().startswith('[') else f'[{ac}]'
    return "[Top, Right, Bottom]"

def bool_present(text: str, key: str) -> bool:
    return re.search(rf'(?im)^\s*{re.escape(key)}\s*=', text) is not None

def extract_id(old_text: str) -> str | None:
    return find_top_assign(old_text, "ID")

def extract_old_namekey(old_text: str) -> str | None:
    return find_top_assign(old_text, "NameKey")

def build_components_block(old_text: str, verts_sets):
    lines = []
    lines.append('\tComponents : ^/0/Components')
    lines.append('\t{')
    # Collider from first verts set (if any)
    if verts_sets:
        lines.append('\t\tCollider')
        lines.append('\t\t{')
        lines.append('\t\t\tType = PolygonCollider')
        lines.append('\t\t\tVertices')
        lines.append('\t\t\t[')
        for x,y in verts_sets[0]:
            # match style [0.75, 0]
            # ensure integers are printed without .0
            xs = str(int(x)) if x.is_integer() else str(x)
            ys = str(int(y)) if y.is_integer() else str(y)
            lines.append(f'\t\t\t\t[{xs}, {ys}]')
        lines.append('\t\t\t]')
        lines.append('\t\t}')
        lines.append('')

    # ConstructionEffects (standardized)
    lines.append('\t\tConstructionEffects : ^/0/ConstructionEffects')
    lines.append('\t\t{')
    lines.append('\t\t\tLocation = [.5, .5]')
    lines.append('\t\t\tAtlasSprite')
    lines.append('\t\t\t{')
    lines.append('\t\t\t\tFile = "structure_mask_combined.png"')
    lines.append('\t\t\t\tNormalsFile = "structure_normals.png"')
    lines.append('\t\t\t\tSize = [1, 1]')
    lines.append('\t\t\t\t//VertexColor = [255, 0, 0, 255]')
    lines.append('\t\t\t}')
    lines.append('\t\t}')
    lines.append('')

    # Graphics (standardized)
    lines.append('\t\tGraphics')
    lines.append('\t\t{')
    lines.append('\t\t\tType = Graphics')
    lines.append('\t\t\tLocation = [0.5, 0.5]')
    lines.append('\t\t\tFloor')
    lines.append('\t\t\t{')
    lines.append('\t\t\t\tLayer = "structure"')
    lines.append('\t\t\t\tDamageLevels')
    lines.append('\t\t\t\t[')
    lines.append('\t\t\t\t\t{')
    lines.append('\t\t\t\t\t\tFile = "structure.png"')
    lines.append('\t\t\t\t\t\tNormalsFile = "structure_normals.png"')
    lines.append('\t\t\t\t\t\tSize = [1, 1]')
    lines.append('\t\t\t\t\t}')
    lines.append('\t\t\t\t\t{')
    lines.append('\t\t\t\t\t\tFile = "structure_33.png"')
    lines.append('\t\t\t\t\t\tNormalsFile = "structure_33_normals.png"')
    lines.append('\t\t\t\t\t\tSize = [1, 1]')
    lines.append('\t\t\t\t\t}')
    lines.append('\t\t\t\t\t{')
    lines.append('\t\t\t\t\t\tFile = "structure_66.png"')
    lines.append('\t\t\t\t\t\tNormalsFile = "structure_66_normals.png"')
    lines.append('\t\t\t\t\t\tSize = [1, 1]')
    lines.append('\t\t\t\t\t}')
    lines.append('\t\t\t\t]')
    lines.append('\t\t\t}')
    lines.append('\t\t}')
    lines.append('')

    # DestroyedEffects
    lines.append('\t\tDestroyedEffects')
    lines.append('\t\t{')
    lines.append('\t\t\tType = DeathEffects')
    lines.append('\t\t\tMediaEffects = &/COMMON_EFFECTS/StructureDestroyed')
    lines.append('\t\t\tLocation = [.5, .5]')
    lines.append('\t\t}')
    lines.append('')

    # Blueprints
    lines.append('\t\tBlueprints')
    lines.append('\t\t{')
    lines.append('\t\t\tType = BlueprintSprite')
    lines.append('\t\t\tFile = "blueprints.png"')
    lines.append('\t\t\tSize = [1, 1]')
    lines.append('\t\t}')
    lines.append('\t}')
    return "\n".join(lines)

def build_editor_icon_block():
    return """\tEditorIcon
\t{
\t\tTexture
\t\t{
\t\t\tFile = "icon.png"
\t\t\tSampleMode = Linear
\t\t}
\t\tSize = [32, 32]
\t}"""

def build_new_file(old_text: str, filename: str) -> str:
    id_val = extract_id(old_text) or "SW.unknown_id"
    old_namekey = extract_old_namekey(old_text) or '"Parts/Structure_Unknown"'
    old_name_plain = old_namekey.strip().strip('"')
    new_namekey = pascalize_namekey_fragment(old_name_plain)
    new_icon = name_to_icon(new_namekey)
    allowed_contiguity = format_allowed_contiguity(old_text)
    scale = infer_scale(old_text, filename)

    # Parse vertices from any old CustomCollider
    verts_sets = extract_all_customcollider_vertices(old_text)

    # Booleans / options
    is_rotateable = bool_present(old_text, "IsRotateable") or True  # default true

    out = []
    out.append('Part : <../base_part_terran_structure.rules>/Part')
    out.append('{')
    out.append(f'\tNameKey = "{new_namekey}"')
    out.append(f'\tIconNameKey = "{new_icon}"')
    out.append(f'\tID = {id_val}')
    out.append('\tEditorGroup = "Structure"\n')
    out.append('\tResources')
    out.append('\t[')
    out.append('\t\t[steel, ceil((ceil((&<../base_part_terran_structure.rules>/Cost)*(&~/Scale)))/4)]')
    out.append('\t]')
    out.append(f'\tAllowedContiguity = {allowed_contiguity}')
    out.append('\tMaxHealth = floor((&<../base_part_terran_structure.rules>/DefaultHealth) * (&~/Scale))')
    out.append('\tInitialPenetrationResistance = ceil((&<../base_part_terran_structure.rules>/DefaultInitialPenetrationResistance) * (&~/Scale) * 0.9)')
    out.append('\tDensity = (&<../base_part_terran_structure.rules>/DefaultDensity)')
    out.append('\tCellOccupancyFactor = ceil((&~/Scale))')
    out.append(f'\tIsRotateable = {"true" if is_rotateable else "false"}')
    out.append('\tVirtualInternalCells')
    out.append('\t[')
    out.append('\t\t{ExternalCell=[0, -1]; InternalCell=[1, 0]}')
    out.append('\t\t{ExternalCell=[0, 1]; InternalCell=[1, 0]}')
    out.append('\t]')
    out.append('\t//FlipHRotate = [2, 1, 0, 3]')
    out.append('\t//FlipVRotate = [0, 3, 2, 1]')
    out.append('\tGenerateRectCollider = false')

    # EditorIcon block
    out.append(build_editor_icon_block())

    # Components (constructed to target format)
    out.append(build_components_block(old_text, verts_sets))

    out.append('}')
    out.append(f'Scale = ({scale})\n')
    return "\n".join(out)

def convert_file(p: Path, out_suffix="_converted.rules") -> Path:
    old_text = read_text(p)
    new_text = build_new_file(old_text, p.name)
    out = p.with_name(p.stem + out_suffix)
    write_text(out, new_text)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="Folder to scan")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return

    candidates = []
    for ext in (".rules", ".bak"):
        for p in folder.rglob(f"*{ext}"):
            if p.name.lower().startswith("structure_") and not p.stem.lower().endswith("_converted"):
                candidates.append(p)

    if not candidates:
        print("No matching files found.")
        return

    print(f"Found {len(candidates)} candidate file(s).")
    for p in sorted(candidates):
        out = p.with_name(p.stem + "_converted.rules")
        if args.dry_run:
            print(f"- would create: {out.name} from {p.name}")
        else:
            print(f"- creating: {out.name} from {p.name}")
            convert_file(p)

if __name__ == "__main__":
    main()
