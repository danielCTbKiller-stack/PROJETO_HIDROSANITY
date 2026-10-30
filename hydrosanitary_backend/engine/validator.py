class HydraulicValidator:
    """Validador de conformidade normativa para trechos hidráulicos."""

    @staticmethod
    def validate_pipe_limits(pipe_id: str, velocity: float, max_allowable_velocity: float = 3.0) -> dict:
        """Valida se o trecho atende aos limites normativos de velocidade e ruído."""
        if velocity > max_allowable_velocity:
            return {
                "level": "ALERTA",
                "code": "HIGH_VELOCITY",
                "message": f"Trecho {pipe_id}: Velocidade de {velocity:.2f} m/s excede o limite máximo de {max_allowable_velocity} m/s (Risco de ruído e golpe de aríete).",
            }
        elif velocity < 0.3:
            return {
                "level": "INFO",
                "code": "LOW_VELOCITY",
                "message": f"Trecho {pipe_id}: Velocidade baixa ({velocity:.2f} m/s). Atenção à retenção de ar.",
            }

        return {
            "level": "OK",
            "code": "APPROVED",
            "message": f"Trecho {pipe_id}: Velocidade aprovada ({velocity:.2f} m/s).",
        }
