from datetime import datetime, timezone
import structlog
from integrations.supabase_client import get_supabase
from integrations.dropshipping_api import dropshipping_api
import re

log = structlog.get_logger()

def extract_phone_parts(raw_phone: str, default_indicativo: str = "+57") -> tuple[str, str]:
    """
    Parsea un teléfono crudo y separa el indicativo del número base.
    Evita redundancias como tener indicativo +57 y número 573001234567.
    """
    if not raw_phone or str(raw_phone).strip() == "":
        return default_indicativo, ""
        
    # Limpiar todo lo que no sea número
    clean = re.sub(r"\D", "", str(raw_phone))
    
    # Si tiene 12 dígitos y empieza por 57 (Colombia móvil)
    if len(clean) == 12 and clean.startswith("57"):
        return "+57", clean[2:]
    
    # Si tiene 10 dígitos (Colombia fijo o móvil sin indicativo)
    if len(clean) == 10:
        return default_indicativo, clean
        
    # En caso de otros países, si no podemos deducir de forma segura, 
    # dejamos el default y guardamos el número como venga (pero limpio)
    return default_indicativo, clean

async def submit_order_to_supabase(
    nombres: str,
    apellidos: str,
    whatsapp: str,
    departamento: str,
    ciudad: str,
    main_address: str,
    neighborhood: str,
    producto: str,
    valor_a_pagar: str,
    reference_point: str = "",
    order_id: str = None,
    indicativo_pais: str = "+57",
    numero_alternativo: str = "",
    notas_adicionales: str = "",
    notas: str | None = None,
    email: str = "",
    metodo_pago: str = "Contraentrega",
    oferta: str = "Precio Regular",
    sku: str = "",
    dropi_product_id: int = None,
    caller_whatsapp: str = None
) -> dict:
    """
    Registra o actualiza un pedido final en el sistema (Supabase).
    Retorna {'id': order_id, 'message': '...'}
    """
    # 1. Preparar datos
    if notas is not None and notas != "":
        notas_adicionales = notas
    clean_value = str(valor_a_pagar).replace("$", "").replace(".", "").replace(" ", "").strip()
    try:
        final_value = float(clean_value)
    except ValueError:
        final_value = 0.0

    # Limpieza exhaustiva de teléfonos para evitar redundancias
    ind_wp, wp_clean = extract_phone_parts(whatsapp, indicativo_pais)
    ind_alt, alt_clean = extract_phone_parts(numero_alternativo, indicativo_pais) if numero_alternativo else ("", "")

    order_data_supabase = {
        "Nombres": nombres,
        "Apellidos": apellidos,
        "Indicativo Pais": ind_wp,
        "Whatsapp": wp_clean,
        "Número Alternativo": alt_clean,
        "Departamento": departamento,
        "Ciudad": ciudad,
        "Dirección": main_address,
        "Notas_Adicionales": (f"Barrio: {neighborhood}" if neighborhood else "") + (f" - Ref: {reference_point}" if reference_point else "") + (f" - {notas_adicionales}" if notas_adicionales else ""),
        "email": email,
        "Método de pago": metodo_pago,
        "Producto": producto,
        "Oferta": oferta,
        "SKU": sku,
        "Status": "Creado",
        "Tracking Number": "",
        "Valor a Pagar": final_value,
        "Timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    
    # IMPORTANTE: NO agregamos "Order ID" al payload order_data_supabase
    # porque es una columna GENERATED ALWAYS en Supabase y causará error 428C9.

    # 2. Enviar a Supabase (Upsert) - Ejecutado en hilo separado para no bloquear
    import asyncio
    
    def _sync_upsert():
        supabase = get_supabase()
        
        # Validar inmutabilidad si se está actualizando un pedido
        if order_id:
            clean_id = str(order_id).replace("P-", "").lstrip("0")
            try:
                # El "Order ID" debe ser entero en la base de datos
                int_clean_id = int(clean_id)
                existing = supabase.table("ORDERS").select('"Tracking Number", "Status", "Whatsapp"').eq("Order ID", int_clean_id).execute()
                if not existing.data:
                    raise ValueError(f"No se encontro el pedido {order_id}; no se creo un pedido nuevo.")
                
                if existing.data:
                    # 1. Validar propiedad del pedido
                    db_phone = existing.data[0].get("Whatsapp")
                    db_clean = str(db_phone)[-10:] if db_phone else ""
                    caller_clean = str(caller_whatsapp)[-10:] if caller_whatsapp and caller_whatsapp != "admin" else ""
                    
                    if caller_whatsapp and caller_whatsapp != "admin" and db_clean != caller_clean:
                        raise ValueError("Acceso Denegado: Solo el número que creó el pedido original puede modificarlo.")

                    # 2. Validar inmutabilidad de estados logísticos
                    current_status = existing.data[0].get("Status")
                    if current_status == "Anulado":
                        raise ValueError(f"Este pedido ya fue anulado y no puede ser modificado.")
                    if existing.data[0].get("Tracking Number"):
                        raise ValueError(f"Este pedido ya posee un número de guía y se encuentra en gestión logística. Imposible editar o anular. Lee las Delivery Notes para más detalles.")
                
                # Ejecutar UPDATE explícito para no chocar con IDENTITY GENERATED ALWAYS
                return supabase.table("ORDERS").update(order_data_supabase).eq("Order ID", int_clean_id).select('"Order ID"').execute()
            except ValueError as ve:
                if "despachado" in str(ve) or "anulado" in str(ve):
                    raise ve
                # Si el int(clean_id) falla, lo intentamos como string o lo dejamos pasar
                raise ve

        # Ejecutar INSERT si no hay order_id (o si falló la validación del int anterior y no retornó)
        if order_id:
            raise ValueError(f"No se pudo actualizar el pedido {order_id}; no se creo un pedido nuevo.")

        return supabase.table("ORDERS").insert(order_data_supabase).select('"Order ID"').execute()

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _sync_upsert)
        
        if response.data:
            new_id = response.data[0].get("Order ID")
            if new_id is not None:
                formatted_id = f"P-{int(new_id):06d}"
            else:
                formatted_id = "P-UNKNOWN"
            log.info("order.submitted", id=formatted_id, update=bool(order_id))
            return {
                "id": formatted_id,
                "message": f"✅ Pedido {'actualizado' if order_id else 'registrado'} exitosamente. El ID es {formatted_id}."
            }
        else:
            return {"id": None, "message": "⚠️ No se recibió confirmación de Supabase."}
    except Exception as e:
        log.error("order.submit_failed", error=str(e))
        return {"id": None, "message": f"❌ Error en Supabase: {str(e)}"}

async def update_order_status(order_id: str, status: str, caller_whatsapp: str = None) -> dict:
    """Actualiza únicamente el estado de un pedido en Supabase (ej: 'Anulado')."""
    import asyncio
    
    def _sync_update():
        supabase = get_supabase()
        clean_id = str(order_id).replace("P-", "").lstrip("0")
        try:
            int_id = int(clean_id)
            
            # Validación estricta antes de actualizar
            existing = supabase.table("ORDERS").select('"Tracking Number", "Whatsapp"').eq("Order ID", int_id).execute()
            if existing.data:
                db_phone = existing.data[0].get("Whatsapp")
                db_clean = str(db_phone)[-10:] if db_phone else ""
                caller_clean = str(caller_whatsapp)[-10:] if caller_whatsapp and caller_whatsapp != "admin" else ""
                
                if caller_whatsapp and caller_whatsapp != "admin" and db_clean != caller_clean:
                    raise ValueError("Acceso Denegado: Solo el número que creó el pedido original puede modificarlo.")
                if existing.data[0].get("Tracking Number"):
                    raise ValueError("Este pedido ya posee un número de guía y se encuentra en gestión logística. Imposible editar o anular. Lee las Delivery Notes para más detalles.")
            
            return supabase.table("ORDERS").update({"Status": status, "Timestamp": datetime.now(timezone.utc).isoformat()}).eq("Order ID", int_id).select('"Order ID"').execute()
        except ValueError as ve:
            if "Acceso" in str(ve) or "guía" in str(ve): raise ve
            raise ValueError(f"ID de pedido inválido: {order_id}")
            
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _sync_update)
        if response.data:
            return {"id": order_id, "message": f"✅ Estado del pedido {order_id} actualizado a '{status}'."}
        else:
            return {"id": None, "message": f"⚠️ No se encontró el pedido {order_id}."}
    except Exception as e:
        log.error("order.status_update_failed", error=str(e))
        return {"id": None, "message": f"❌ Error: {str(e)}"}

async def add_order_note(order_id: str, notas_adicionales: str, caller_whatsapp: str = None) -> dict:
    """
    Agrega texto a la columna 'Notas_Adicionales' de un pedido sin alterar otros campos.
    Esta función NO ESTÁ SUJETA A LA RESTRICCIÓN DE INMUTABILIDAD LOGÍSTICA. 
    Es decir, puedes agregar notas a un pedido que ya tiene guía de envío (por ejemplo, para reportar que el cliente solicitó un cambio de dirección).
    """
    import asyncio
    
    def _sync_add_note():
        supabase = get_supabase()
        clean_id = str(order_id).replace("P-", "").lstrip("0")
        try:
            int_id = int(clean_id)
            # Primero leemos las notas actuales para hacer un "append" y no borrarlas
            existing = supabase.table("ORDERS").select('"Notas_Adicionales", "Whatsapp"').eq("Order ID", int_id).execute()
            if not existing.data:
                raise ValueError(f"No se encontró el pedido {order_id}")
                
            db_phone = existing.data[0].get("Whatsapp")
            db_clean = str(db_phone)[-10:] if db_phone else ""
            caller_clean = str(caller_whatsapp)[-10:] if caller_whatsapp and caller_whatsapp != "admin" else ""
            
            if caller_whatsapp and caller_whatsapp != "admin" and db_clean != caller_clean:
                raise ValueError("Acceso Denegado: Solo el titular puede agregar notas a este pedido.")
                
            notas_actuales = existing.data[0].get("Notas_Adicionales") or ""
            nueva_nota = f"{notas_actuales}\n[Update]: {notas_adicionales}".strip()
            
            return supabase.table("ORDERS").update({"Notas_Adicionales": nueva_nota}).eq("Order ID", int_id).select('"Order ID"').execute()
        except Exception as e:
            raise e
            
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _sync_add_note)
        if response.data:
            return {"id": order_id, "message": f"✅ Nota agregada exitosamente al pedido {order_id}."}
        else:
            return {"id": None, "message": f"⚠️ No se encontró el pedido {order_id}."}
    except Exception as e:
        log.error("order.add_note_failed", error=str(e))
        return {"id": None, "message": f"❌ Error al agregar la nota: {str(e)}"}

    # 3. Enviar a Dropi.co (DESACTIVADO TEMPORALMENTE PARA PRUEBAS)
    # dropi_payload = {
    #     "customer": {
    #         "name": f"{nombres} {apellidos}",
    #         "phone": whatsapp,
    #         "email": email or f"{whatsapp}@vitalenergy.com",
    #         "address": direccion,
    #         "city": ciudad,
    #         "state": departamento,
    #         "country": "CO"
    #     },
    #     "items": [
    #         {
    #             "product_id": dropi_product_id or 0,
    #             "quantity": 1,
    #             "price": final_value
    #         }
    #     ],
    #     "payment_method": "COD" if metodo_pago.lower() == "contraentrega" else "PREPAID"
    # }

    # try:
    #     dropi_res = await dropshipping_api.create_order(dropi_payload)
    #     if dropi_res.get("success"):
    #         print("DEBUG: Montado en Dropi OK.")
    #         results.append("✅ Pedido montado exitosamente en Dropi.co.")
    #     else:
    #         results.append(f"❌ Error Dropi: {dropi_res.get('error')}")
    # except Exception as e:
    #     results.append(f"❌ Excepción Dropi: {e}")
