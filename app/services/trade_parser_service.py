# app/services/trade_parser_service.py

import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import List, Dict
from pathlib import Path
from app.schemas.trade import Trade

logger = logging.getLogger(__name__)

class TradeParserService:
    """Parsear operaciones desde CSV o XLSX exportado de MT5"""
    
    @staticmethod
    def load_trades_from_file(file_path: str) -> List[Trade]:
        """Cargar operaciones desde archivo CSV o XLSX"""
        try:
            # Detectar extensión del archivo
            file_extension = Path(file_path).suffix.lower()
            
            # Leer archivo según extensión
            if file_extension == '.csv':
                df = pd.read_csv(file_path, encoding='utf-8')
                logger.info(f"📄 Leyendo archivo CSV: {file_path}")
            elif file_extension in ['.xlsx', '.xls']:
                # Leer primero sin header para buscar dónde empiezan los datos
                df_temp = pd.read_excel(file_path, engine='openpyxl', header=None)
                
                # Buscar la fila del encabezado
                header_row_idx = -1
                for idx, row in df_temp.iterrows():
                    row_str = row.astype(str).str.lower().tolist()
                    if 'time' in row_str and 'symbol' in row_str:
                        header_row_idx = idx
                        break
                
                if header_row_idx != -1:
                    # Volver a leer usando la fila correcta como header
                    df = pd.read_excel(file_path, engine='openpyxl', header=header_row_idx)
                    logger.info(f"📊 Header encontrado en fila {header_row_idx}")
                else:
                    # Si no se encuentra, intentar leer normal (quizás ya está limpio)
                    df = pd.read_excel(file_path, engine='openpyxl')
                    logger.info(f"📊 No se detectó fila de header específica, leyendo normal")

            else:
                raise ValueError(f"Formato de archivo no soportado: {file_extension}. Use .csv o .xlsx")
            
            # Mostrar columnas originales para debug
            logger.info(f"📋 Columnas encontradas: {list(df.columns)}")
            
            # Normalize column names: handle duplicate columns (Time, Time.1) and all naming conventions
            column_mapping = {
                # Duplicate columns from MT5 HTML/Excel exports
                'Time': 'open_time',
                'Time.1': 'close_time',
                'Price': 'open_price',
                'Price.1': 'close_price',
                # Explicit Open/Close column variations
                'Open Time': 'open_time',
                'Close Time': 'close_time',
                'Open Price': 'open_price',
                'Close Price': 'close_price',
                'Symbol': 'symbol',
                'Type': 'order_type',
                'Volume': 'volume',
                'Profit': 'profit_usd',
                'Commission': 'commission',
                'Swap': 'swap',
                'S / L': 'sl',
                'T / P': 'tp',
                'Comment': 'comment',
                # Spanish variants
                'Hora de Apertura': 'open_time',
                'Hora de Cierre': 'close_time',
                'Precio de Apertura': 'open_price',
                'Precio de Cierre': 'close_price',
                'Símbolo': 'symbol',
                'Simbolo': 'symbol',
                'Tipo': 'order_type',
                'Volumen': 'volume',
                'Ganancias': 'profit_usd',
                'Beneficio': 'profit_usd',
                'Comisión': 'commission',
                'Comision': 'commission',
                'Comente': 'comment',
                'Comentario': 'comment',
            }
            df.rename(columns=column_mapping, inplace=True)

            # Secondary pass: normalize remaining columns (strip spaces, lowercase, replace spaces with underscores)
            def normalize_col(c: str) -> str:
                c_clean = str(c).strip().lower().replace(' ', '_')
                aliases = {
                    'open_time': 'open_time',
                    'opentime': 'open_time',
                    'close_time': 'close_time',
                    'closetime': 'close_time',
                    'open_price': 'open_price',
                    'openprice': 'open_price',
                    'close_price': 'close_price',
                    'closeprice': 'close_price',
                    'symbol': 'symbol',
                    'type': 'order_type',
                    'order_type': 'order_type',
                    'ordertype': 'order_type',
                    'volume': 'volume',
                    'lots': 'volume',
                    'profit': 'profit_usd',
                    'profit_usd': 'profit_usd',
                    'pnl': 'profit_usd',
                    'commission': 'commission',
                    'swap': 'swap',
                    'sl': 'sl',
                    'tp': 'tp',
                    'comment': 'comment'
                }
                return aliases.get(c_clean, c_clean)

            df.columns = [normalize_col(c) for c in df.columns]
            required_columns = ['open_time', 'close_time', 'symbol', 'order_type', 'volume', 'open_price', 'close_price', 'profit_usd']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                error_msg = f"❌ Faltan columnas requeridas: {missing_columns}\n"
                error_msg += f"📋 Columnas disponibles: {list(df.columns)}\n"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            trades = []
            for idx, row in df.iterrows():
                try:
                    # Ignorar filas que no sean operaciones (ej: balance inicial, totales)
                    if pd.isna(row['symbol']) or str(row['order_type']).lower() not in ['buy', 'sell']:
                        continue
                        
                    # Calcular profit_pct de forma segura
                    try:
                        profit_pct = (float(row['profit_usd']) / abs(float(row['open_price']) * float(row['volume']) * 100)) * 100
                    except (ZeroDivisionError, ValueError):
                        profit_pct = 0.0
                    
                    # Calcular duración
                    try:
                        # Manejar formato de fecha con puntos (2025.07.08 15:52:55)
                        open_dt = pd.to_datetime(str(row['open_time']).replace('.', '-'))
                        close_dt = pd.to_datetime(str(row['close_time']).replace('.', '-'))
                        duration = int((close_dt - open_dt).total_seconds() / 60)
                    except:
                        duration = 0
                        open_dt = row['open_time'] # Fallback
                        close_dt = row['close_time'] # Fallback
                    
                    trade = Trade(
                        id=int(idx),
                        open_time=open_dt,
                        close_time=close_dt,
                        symbol=str(row['symbol']).strip(),
                        order_type=str(row['order_type']).upper(),
                        volume=float(row['volume']),
                        open_price=float(row['open_price']),
                        close_price=float(row['close_price']),
                        profit_usd=float(row['profit_usd']),
                        profit_pct=profit_pct,
                        duration=duration,
                        spread=float(row.get('spread', 0)) if 'spread' in row else None,
                        comment=str(row.get('comment', '')) if 'comment' in row else None,
                        status='GANADOR' if float(row['profit_usd']) > 0 else ('PERDEDOR' if float(row['profit_usd']) < 0 else 'BREAK_EVEN')
                    )
                    trades.append(trade)
                except Exception as row_error:
                    logger.warning(f"⚠️ Saltando fila {idx} por error: {row_error}")
                    continue
            
            logger.info(f"✅ Cargadas {len(trades)} operaciones desde {file_path}")
            return trades
            
        except Exception as e:
            logger.error(f"❌ Error cargando CSV: {e}")
            raise

    @staticmethod
    def validate_trade_data(trades: List[Trade]) -> bool:
        """Validar integridad de datos"""
        if not trades:
            logger.warning("⚠️ No hay operaciones para validar")
            return False
        
        logger.info(f"✅ Validadas {len(trades)} operaciones")
        return True
