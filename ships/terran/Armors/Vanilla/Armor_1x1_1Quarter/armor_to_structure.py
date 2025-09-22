#!/usr/bin/env python3
import re, argparse, pathlib

STRUCT_BASE = '<../base_part_terran_structure.rules>/Part'
STRUCT_COST   = '&<../base_part_terran_structure.rules>/Cost'
STRUCT_H = '&<../base_part_terran_structure.rules>/DefaultHealth'
STRUCT_IPR = '&<../base_part_terran_structure.rules>/DefaultInitialPenetrationResistance'
STRUCT_D = '&<../base_part_terran_structure.rules>/DefaultDensity'

def sub_multiline(pattern, repl, text, flags=re.DOTALL):
    return re.sub(pattern, repl, text, flags=flags)

def remove_block_by_name(text, name):
    # Removes a top-level block "name { ... }" non-greedily.
    return re.sub(r'\n\s*' + re.escape(name) + r'\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*\n', '\n', text, flags=re.DOTALL)

def remove_named_blocks(text, names):
    for n in names:
        text = remove_block_by_name(text, n)
    return text

def normalize_inheritance(text):
    return re.sub(
        r'Part\s*:\s*(?:&\s*)?<\s*\.\./base_part_terran\.rules\s*>\s*/\s*Part',
        f'Part : {STRUCT_BASE}',
        text
    )

def bump_to_structure_keys(text):
    # Name/Icon/ID Armor->Structure
    text = re.sub(r'("Parts/)([^"]*?)Armor', r'\1\2Structure', text)
    text = re.sub(r'IconNameKey\s*=\s*"Parts/([^"]*?)Armor', r'IconNameKey = "Parts/\1Structure', text)
    text = re.sub(r'\bID\s*=\s*([^\s]+)', lambda m: m.group(0).replace('armor','structure').replace('Armor','Structure'), text)
    # Remove UnderlyingPart lines (armor-style)
    text = re.sub(r'^\s*UnderlyingPart[^\n]*\n', '', text, flags=re.MULTILINE)
    # Insert EditorGroup after ID if not present
    if 'EditorGroup' not in text:
        text = re.sub(r'(\bID\s*=\s*[^\n]+\n)', r'\1\tEditorGroup = "Structure"\n', text)
    return text

def rewrite_resources(text):
    # Replace entire Resources array with structure version (keeps outer array but rewrites steel line)
    def repl_resources(m):
        return (
            'Resources\n'
            '\t[\n'
            f'\t\t[steel, ceil((ceil(({STRUCT_COST})*(&~/Scale)))/4)]\n'
            '\t]\n'
        )
    return re.sub(r'Resources\s*\[\s*(?:.|\n)*?\]', repl_resources, text)

def rewrite_stats_defaults(text):
    # Replace MaxHealth, InitialPenetrationResistance, Density to structure defaults
    text = re.sub(r'^\s*MaxHealth\s*=.*$', f'\tMaxHealth = floor(({STRUCT_H}) * (&~/Scale))', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*InitialPenetrationResistance\s*=.*$', f'\tInitialPenetrationResistance = ceil(({STRUCT_IPR}) * (&~/Scale) * 0.9)', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*Density\s*=.*$', f'\tDensity = ({STRUCT_D})', text, flags=re.MULTILINE)
    # If any of the three were missing, append them just after AllowedContiguity or Size
    anchor = re.search(r'^\s*AllowedContiguity\s*=\s*\[[^\]]*\]\s*$', text, flags=re.MULTILINE) or \
             re.search(r'^\s*Size\s*=\s*\[[^\]]*\]\s*$', text, flags=re.MULTILINE)
    inserts = (
        f'\tMaxHealth = floor(({STRUCT_H}) * (&~/Scale))\n'
        f'\tInitialPenetrationResistance = ceil(({STRUCT_IPR}) * (&~/Scale) * 0.9)\n'
        f'\tDensity = ({STRUCT_D})\n'
    )
    # Ensure all present
    need_insert = any(k not in text for k in ['DefaultHealth','DefaultInitialPenetrationResistance','DefaultDensity']) \
                  or not re.search(r'^\s*MaxHealth\s*=', text, flags=re.MULTILINE) \
                  or not re.search(r'^\s*InitialPenetrationResistance\s*=', text, flags=re.MULTILINE) \
                  or not re.search(r'^\s*Density\s*=', text, flags=re.MULTILINE)
    if need_insert and anchor:
        pos = anchor.end()
        text = text[:pos] + '\n' + inserts + text[pos:]
    return text

def add_structure_extras(text):
    # Add CellOccupancyFactor & IsRotateable (present or not)
    if not re.search(r'^\s*CellOccupancyFactor\s*=', text, flags=re.MULTILINE):
        text = re.sub(r'^\s*Density\s*=\s*[^\n]+', lambda m: m.group(0) + '\n\tCellOccupancyFactor = ceil((&~/Scale))', text, flags=re.MULTILINE)
    if not re.search(r'^\s*IsRotateable\s*=', text, flags=re.MULTILINE):
        text = re.sub(r'^\s*CellOccupancyFactor\s*=\s*[^\n]+', lambda m: m.group(0) + '\n\tIsRotateable = true', text, flags=re.MULTILINE)
    return text

def scrub_armor_only_fields(text):
    # Remove lines
    for key in ['ExternalWalls', 'InternalWalls', 'SelectionTypeID', 'UnderlyingPartPerTile', 'EditorReplacementPartID']:
        text = re.sub(r'^\s*' + key + r'\s*=.*\n', '', text, flags=re.MULTILINE)
    # Remove blocks
    text = remove_named_blocks(text, ['EmpAbsorber', 'Stats'])
    return text

def fix_editoricon(text):
    # SampleMode Point -> Linear, remove MipLevels
    text = re.sub(r'(EditorIcon\s*\{(?:[^{}]|\{[^{}]*\})*?File\s*=\s*"[^"]+"\s*[^{}]*?)\bSampleMode\s*=\s*Point', r'\1SampleMode = Linear', text, flags=re.DOTALL)
    text = re.sub(r'^\s*MipLevels\s*=\s*max\s*$', '', text, flags=re.MULTILINE)
    return text

def components_inheritance_and_cleanup(text):
    # Ensure Components : ^/0/Components (drop , &<roofs.rules>)
    text = re.sub(r'(Components\s*:\s*\^/0/Components)\s*,\s*&<[^>]+roofs\.rules>', r'\1', text)
    # Remove RoofArtOptionToggle block if present
    text = remove_block_by_name(text, 'RoofArtOptionToggle')
    return text

def ensure_construction_effects(text):
    # Inject/replace ConstructionEffects block inside Components
    def repl_components(m):
        block = m.group(0)
        # Remove any existing ConstructionEffects block (we’ll re-add)
        block2 = remove_block_by_name(block, 'ConstructionEffects')
        # Prepare insertion just before Graphics block in Components
        construct = (
            '\n\t\tConstructionEffects : ^/0/ConstructionEffects\n'
            '\t\t{\n'
            '\t\t\tLocation = [.5, .5]\n'
            '\t\t\tAtlasSprite\n'
            '\t\t\t{\n'
            '\t\t\t\tFile = "structure_mask_combined.png"\n'
            '\t\t\t\tNormalsFile = "structure_normals.png"\n'
            '\t\t\t\tSize = [1, 1]\n'
            '\t\t\t\t//VertexColor = [255, 0, 0, 255]\n'
            '\t\t\t}\n'
            '\t\t}\n'
        )
        block2 = re.sub(r'(\n\s*\tGraphics\s*\{)', construct + r'\1', block2, count=1)
        return block2
    return re.sub(r'(Components\s*:[^{]*\{(?:[^{}]|\{[^{}]*\})*\})', repl_components, text, flags=re.DOTALL)

def rewrite_graphics_to_structure(text):
    # Remove entire Walls graphics block inside Components/Graphics
    text = sub_multiline(r'\n\s*Walls\s*\{(?:[^{}]|\{[^{}]*\})*\}', '', text)

    # Floor → Layer "structure"
    text = re.sub(r'(Floor\s*\{\s*\{?[^{}]*?)\bLayer\s*=\s*"floors"', r'\1Layer = "structure"', text)

    # Remove UVRotation lines anywhere in Graphics
    text = re.sub(r'^\s*UVRotation\s*=\s*[^\n]+\n', '', text, flags=re.MULTILINE)

    # armor*.png -> structure*.png (File fields)
    text = re.sub(r'(File\s*=\s*")([^"]*?)armor(_\d{2})?(\.png")',
                  lambda m: f'{m.group(1)}{m.group(2)}structure{m.group(3) or ""}{m.group(4)}', text)

    # Add NormalsFile for each structure damage level if missing.
    def add_normals_for_damagelevel(block):
        # Determine filename to synthesize the normals name
        file_match = re.search(r'File\s*=\s*"([^"]+)"', block)
        if not file_match:
            return block
        fname = file_match.group(1)
        # Compute normals name
        base = fname.replace('.png','')
        normals = base + '_normals.png' if not base.endswith('_normals') else base + '.png'
        if 'NormalsFile' not in block:
            block = re.sub(r'(Size\s*=\s*\[[^\]]+\]\s*\n)', r'\1\t\t\t\tNormalsFile = "' + normals + '"\n', block, count=1)
        return block

    def repl_damagelevels(m):
        inner = m.group(1)
        # operate on each { ... } block inside DamageLevels
        inner2 = re.sub(r'(\{\s*(?:[^{}]|\{[^{}]*\})*?\})',
                        lambda mm: add_normals_for_damagelevel(mm.group(1)),
                        inner)
        return 'DamageLevels\n\t\t\t[\n' + inner2 + '\n\t\t\t]'

    text = re.sub(r'DamageLevels\s*\[\s*((?:[^{}\[\]]|\{[^{}]*\})*?)\s*\]', repl_damagelevels, text, flags=re.DOTALL)
    return text

def tweak_destroyed_effects(text):
    # Set StructureDestroyed
    return re.sub(r'(DestroyedEffects\s*\{(?:[^{}]|\{[^{}]*\})*?MediaEffects\s*=\s*)&/COMMON_EFFECTS/[^ \n}]+',
                  r'\1&/COMMON_EFFECTS/StructureDestroyed', text, flags=re.DOTALL)

def final_polish(text):
    # Ensure Components header stays singular: "Type = Graphics" block preserved already.
    # Clean duplicate blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def convert_text(text: str) -> str:
    text = normalize_inheritance(text)
    text = bump_to_structure_keys(text)
    text = rewrite_resources(text)
    text = rewrite_stats_defaults(text)
    text = add_structure_extras(text)
    text = scrub_armor_only_fields(text)
    text = fix_editoricon(text)
    text = components_inheritance_and_cleanup(text)
    text = ensure_construction_effects(text)
    text = rewrite_graphics_to_structure(text)
    text = tweak_destroyed_effects(text)
    text = final_polish(text)
    return text

def main():
    ap = argparse.ArgumentParser(description="Convert armor .rules -> structure .rules (v2, matches target layout).")
    ap.add_argument("input", type=pathlib.Path, help="armor .rules file")
    ap.add_argument("-o","--output", type=pathlib.Path,
                    help="output structure .rules (default: replace armor->structure in filename)")
    args = ap.parse_args()
    text = args.input.read_text(encoding="utf-8")
    out = convert_text(text)
    out_path = args.output
    if not out_path:
        name = args.input.name.replace("armor", "structure").replace("Armor", "Structure")
        out_path = args.input.with_name(name)
    out_path.write_text(out, encoding="utf-8")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
