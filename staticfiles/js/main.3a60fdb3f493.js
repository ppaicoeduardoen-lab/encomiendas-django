document.addEventListener('DOMContentLoaded', function () {
    // ── Inicializar tooltips de Bootstrap ─────────────────────
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(el => new bootstrap.Tooltip(el));

    // ── Auto-cerrar alertas flash después de 5 segundos ───────
    // (complementa la animación CSS del styles.css)
    setTimeout(function () {
        document.querySelectorAll('.alert').forEach(function (alert) {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        });
    }, 5000);

    // ── Confirmación antes de eliminar ────────────────────────
    // Uso en el template: <a href="..." onclick="return confirmar()">Eliminar</a>
    window.confirmar = function (mensaje) {
        return confirm(mensaje || '¿Estás seguro?');
    };

    // ── Resaltar fila al hacer clic (navegación intuitiva) ───────
    // Se movió dentro de DOMContentLoaded para asegurar que los elementos existan
    document.querySelectorAll('.fila-link').forEach(function (fila) {
        fila.addEventListener('click', function () {
            if (this.dataset.href) {
                window.location = this.dataset.href;
            }
        });
    });
});