"""
core/brain/validation.py
-------------------------
Strict schemas for data validation during the sales process.
Uses Pydantic to ensure data integrity before external submissions.
"""
import re
from typing import Optional, Literal
import dns.resolver
from pydantic import BaseModel, Field, validator, EmailStr

import yaml
from pathlib import Path

def _load_business_config():
    path = Path("config/business.yaml")
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return {}

BUSINESS_CFG = _load_business_config()

from core.brain.address_normalizer import standardize_colombian_address

class OrderForm(BaseModel):
    """Esquema de validación AVANZADA — Ahora Dinámico."""
    full_name: str = Field(..., min_length=5)
    email: Optional[EmailStr] = Field(None, description="Correo electrónico válido (Opcional).")
    whatsapp_number: str = Field(..., description="Número de origen de WhatsApp.")
    alternative_phone: Optional[str] = Field(None, description="Número alternativo para llamadas.")
    department: str = Field(..., description="Departamento/Región.")
    city: str = Field(..., description="Ciudad o municipio.")
    
    # Dirección separada
    main_address: str = Field(..., min_length=5, description="Nomenclatura principal con número, apto, torre, etc. (Ej: Calle 15 # 20-30 Apto 4)")
    neighborhood: str = Field(..., description="Nombre del barrio o sector.")
    reference_point: Optional[str] = Field(None, description="Notas adicionales (Ej: 'Frente al parque', 'Rejas blancas').")
    
    payment_method: Literal["Contraentrega", "Transferencia"] = "Contraentrega"
    product_name: str
    quantity: int = Field(..., gt=0)
    sku: Optional[str] = Field(None, description="SKU del producto (si está disponible en el catálogo)")

    @validator("email")
    def validate_email_domain(cls, v):
        """Verifica que el dominio del correo tenga registros MX."""
        if not v:
            return v
        domain = v.split('@')[-1]
        try:
            dns.resolver.resolve(domain, 'MX')
            return v
        except Exception:
            raise ValueError(f"El dominio '{domain}' no parece ser válido o no puede recibir correos.")

    @validator("main_address")
    def validate_address_logic(cls, v):
        """Validación de dirección adaptativa y estandarización automática."""
        industry = BUSINESS_CFG.get("business_info", {}).get("industry", "ecommerce_fisico")
        
        # Primero estandarizamos la dirección usando nuestro algoritmo local
        standardized = standardize_colombian_address(v)
        
        if industry == "ecommerce_fisico":
            patterns = [r"CL", r"CRA", r"DG", r"TV", r"AV", r"AU", r"CQ", r"MZ", r"LT"]
            # En la versión estandarizada, todo está en mayúsculas
            if not any(re.search(r'\b' + p + r'\b', standardized) for p in patterns):
                raise ValueError("La dirección debe incluir nomenclatura clara (ej: Calle, Carrera, Av, etc.).")
            if "#" not in standardized:
                raise ValueError("Falta el número de la dirección (ej: # 12-34).")
                
        return standardized

    @validator("whatsapp_number", "alternative_phone")
    def validate_phones(cls, v):
        if not v or str(v).strip() == "": return None
        clean = re.sub(r"\D", "", str(v))
        
        # Eliminar el prefijo 57 redundante si viene incrustado
        if len(clean) == 12 and clean.startswith("57"):
            clean = clean[2:]
            
        if len(clean) < 7:
            raise ValueError("El número debe tener al menos 7 dígitos.")
        return clean

    @validator("department")
    def validate_department(cls, v):
        valid_deps = BUSINESS_CFG.get("geography", {}).get("valid_departments", [])
        if valid_deps:
            if v.lower() not in [d.lower() for d in valid_deps] and len(v) < 3:
                 raise ValueError(f"'{v}' no es una región válida en {BUSINESS_CFG.get('geography', {}).get('main_region')}.")
        return v.title()

def validate_order(data: dict) -> dict:
    """
    Valida un diccionario de datos de pedido.
    Retorna {'is_valid': True, 'data': ...} o {'is_valid': False, 'errors': [...]}
    """
    # Pre-procesar teléfonos fijos de 7 dígitos según la ciudad (Indicativos de Colombia)
    city = str(data.get("city", "")).lower()
    dept = str(data.get("department", "")).lower()
    loc = city + " " + dept
    
    for field in ["whatsapp_number", "alternative_phone"]:
        val = data.get(field)
        if val:
            clean = re.sub(r"\D", "", str(val))
            if len(clean) == 7:
                prefix = "60" # Default genérico
                if any(x in loc for x in ["medellin", "antioquia", "bello", "envigado", "itagui", "rionegro"]): prefix = "604"
                elif any(x in loc for x in ["bogota", "cundinamarca", "soacha"]): prefix = "601"
                elif any(x in loc for x in ["cali", "valle", "cauca", "nariño"]): prefix = "602"
                elif any(x in loc for x in ["barranquilla", "atlantico", "cartagena", "bolivar", "santa marta", "magdalena", "guajira", "sucre", "cesar", "cordoba"]): prefix = "605"
                elif any(x in loc for x in ["bucaramanga", "santander", "cucuta", "norte de santander"]): prefix = "607"
                elif any(x in loc for x in ["pereira", "risaralda", "manizales", "caldas", "armenia", "quindio"]): prefix = "606"
                elif any(x in loc for x in ["tolima", "ibague", "huila", "neiva", "caqueta", "putumayo"]): prefix = "608"
                
                data[field] = f"{prefix}{clean}"

    try:
        form = OrderForm(**data)
        return {
            "is_valid": True,
            "data": form.dict(),
            "message": "✅ Datos validados correctamente."
        }
    except Exception as e:
        # Extraer mensajes de error amigables
        import json
        errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                field = err["loc"][0]
                msg = err["msg"]
                errors.append(f"Campo '{field}': {msg}")
        else:
            errors.append(str(e))
            
        return {
            "is_valid": False,
            "errors": errors,
            "message": "❌ Faltan datos o hay errores de formato. Por favor, corrígelos con el cliente."
        }
