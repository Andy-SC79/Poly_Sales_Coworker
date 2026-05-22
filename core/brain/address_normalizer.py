import re

def standardize_colombian_address(raw_address: str) -> str:
    """
    Estandariza una dirección colombiana, convirtiéndola a mayúsculas y
    reemplazando prefijos comunes por los estándares logísticos.
    Ej: 'calle 15 kr 20 apto 4 torre 2' -> 'CL 15 CRA 20 APTO 4 TO 2'
    """
    if not raw_address:
        return ""
        
    address = raw_address.upper().strip()
    
    # Reemplazos de vías principales
    replacements = [
        (r'\b(CALLE|CLL|CL)\b', 'CL'),
        (r'\b(CARRERA|CRA|CRR|KR)\b', 'CRA'),
        (r'\b(AVENIDA|AV)\b', 'AV'),
        (r'\b(DIAGONAL|DIAG|DG)\b', 'DG'),
        (r'\b(TRANSVERSAL|TRANS|TV|TRV)\b', 'TV'),
        (r'\b(AUTOPISTA|AUTO|AU)\b', 'AU'),
        (r'\b(BOULEVARD|BLV)\b', 'BLV'),
        (r'\b(CIRCULAR|CIR|CQ)\b', 'CQ'),
        (r'\b(MANZANA|MZ)\b', 'MZ'),
        (r'\b(LOTE|LT)\b', 'LT'),
        
        # Orientaciones
        (r'\b(SUR|S)\b', 'SUR'),
        (r'\b(NORTE|N)\b', 'NORTE'),
        (r'\b(ESTE|E)\b', 'ESTE'),
        (r'\b(OESTE|O)\b', 'OESTE'),
        
        # Propiedad
        (r'\b(APARTAMENTO|APTO|APT|AP)\b', 'APTO'),
        (r'\b(TORRE|TR|TO)\b', 'TO'),
        (r'\b(CASA|CS|CA)\b', 'CS'),
        (r'\b(INTERIOR|INT|IN)\b', 'INT'),
        (r'\b(CONJUNTO|CJ|CONJ)\b', 'CONJ'),
        (r'\b(EDIFICIO|EDIF|ED)\b', 'ED'),
        (r'\b(LOCAL|LC)\b', 'LC'),
        (r'\b(OFICINA|OF)\b', 'OF'),
        (r'\b(BLOQUE|BLQ|BL)\b', 'BL'),
        
        # Normalizar conector "numero", "num", "no" a "#"
        (r'\b(NUMERO|NUM|NO\.|NO)\b', '#'),
        (r'\b(CON|Y)\b', ''), # A veces dicen "calle 20 con 30" -> "CL 20 30"
    ]
    
    for pattern, replacement in replacements:
        address = re.sub(pattern, replacement, address)
        
    # Limpiar espacios dobles
    address = re.sub(r'\s+', ' ', address).strip()
    
    # Asegurar el separador lógico entre la vía y el cruce si el usuario usó guión mal puesto o no usó nada.
    # Por ejemplo, si dicen "CRA 15 20 30" lo ideal es asegurar que haya un "#" y un "-".
    # Esto es más avanzado y peligroso, pero arreglemos algo común: "CL 15 # 20 30" -> "CL 15 # 20 - 30"
    address = re.sub(r'(#\s*\d+[A-Z]?)\s+(\d+[A-Z]?)(?!\s*-)', r'\1 - \2', address)
    
    return address
