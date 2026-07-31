/**
 * Interactive Grid Background - Complete Integration
 * The ENTIRE background is the grid
 */

class InteractiveGridBackground {
    constructor() {
        this.canvas = document.getElementById('gridCanvas');
        this.ctx = this.canvas.getContext('2d');

        this.mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
        this.gridSize = 50;
        this.distortionRadius = 200;
        this.distortionStrength = 25;
        this.gridOffsetX = 0;
        this.gridOffsetY = 0;
        this.wave = 0;

        this.setupCanvas();
        this.attachEventListeners();
        this.animate();
    }

    setupCanvas() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;

        window.addEventListener('resize', () => {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        });
    }

    attachEventListeners() {
        document.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });

        document.addEventListener('mouseleave', () => {
            this.mouse.x = window.innerWidth / 2;
            this.mouse.y = window.innerHeight / 2;
        });
    }

    getGridPoint(gridX, gridY) {
        const x = gridX * this.gridSize + this.gridOffsetX;
        const y = gridY * this.gridSize + this.gridOffsetY;

        // Calculate distance from mouse to this grid point
        const dx = x - this.mouse.x;
        const dy = y - this.mouse.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        let newX = x;
        let newY = y;

        // Apply distortion if within radius
        if (distance < this.distortionRadius && distance > 0) {
            const strength = (1 - distance / this.distortionRadius);
            const angle = Math.atan2(dy, dx);

            // Repulsive force - push points away from mouse
            const repulsion = strength * this.distortionStrength;
            newX = x + Math.cos(angle) * repulsion;
            newY = y + Math.sin(angle) * repulsion;

            // Add wave ripple
            const ripple = Math.sin(distance * 0.02 - this.wave) * strength * 6;
            newX += ripple * Math.cos(angle + Math.PI / 2);
            newY += ripple * Math.sin(angle + Math.PI / 2);
        }

        return { x: newX, y: newY, dist: distance };
    }

    drawBackground() {
        // Draw solid background
        this.ctx.fillStyle = `linear-gradient(135deg, ${getComputedStyle(document.documentElement).getPropertyValue('--canvas')} 0%, #0a0b1a 100%)`;
        const gradient = this.ctx.createLinearGradient(0, 0, this.canvas.width, this.canvas.height);
        gradient.addColorStop(0, '#05060f');
        gradient.addColorStop(1, '#0a0b1a');
        this.ctx.fillStyle = gradient;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    drawGrid() {
        this.wave += 0.03;

        // Calculate grid bounds
        const startX = Math.floor(-this.gridOffsetX / this.gridSize) - 1;
        const startY = Math.floor(-this.gridOffsetY / this.gridSize) - 1;
        const endX = Math.ceil((this.canvas.width - this.gridOffsetX) / this.gridSize) + 1;
        const endY = Math.ceil((this.canvas.height - this.gridOffsetY) / this.gridSize) + 1;

        // Draw horizontal lines
        for (let gridY = startY; gridY <= endY; gridY++) {
            for (let gridX = startX; gridX < endX; gridX++) {
                const p1 = this.getGridPoint(gridX, gridY);
                const p2 = this.getGridPoint(gridX + 1, gridY);

                this.drawLine(p1.x, p1.y, p2.x, p2.y, p1.dist);
            }
        }

        // Draw vertical lines
        for (let gridY = startY; gridY < endY; gridY++) {
            for (let gridX = startX; gridX <= endX; gridX++) {
                const p1 = this.getGridPoint(gridX, gridY);
                const p2 = this.getGridPoint(gridX, gridY + 1);

                this.drawLine(p1.x, p1.y, p2.x, p2.y, p1.dist);
            }
        }

        // Draw intersection dots
        for (let gridY = startY; gridY <= endY; gridY++) {
            for (let gridX = startX; gridX <= endX; gridX++) {
                const point = this.getGridPoint(gridX, gridY);
                this.drawDot(point.x, point.y, point.dist);
            }
        }
    }

    drawLine(x1, y1, x2, y2, distFromMouse) {
        // Determine opacity based on distance from mouse
        let alpha = 0.12;

        if (distFromMouse < this.distortionRadius) {
            const influence = 1 - (distFromMouse / this.distortionRadius);
            alpha = 0.12 + influence * 0.18;
        }

        // Calculate color with influence
        this.ctx.strokeStyle = `rgba(186, 215, 247, ${alpha})`;
        this.ctx.lineWidth = 1;
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        this.ctx.beginPath();
        this.ctx.moveTo(x1, y1);
        this.ctx.lineTo(x2, y2);
        this.ctx.stroke();
    }

    drawDot(x, y, distFromMouse) {
        let size = 1.2;
        let alpha = 0.25;

        if (distFromMouse < this.distortionRadius) {
            const influence = 1 - (distFromMouse / this.distortionRadius);
            size = 1.2 + influence * 2.5;
            alpha = 0.25 + influence * 0.35;
        }

        // Glow effect
        const gradient = this.ctx.createRadialGradient(x, y, 0, x, y, size * 2);
        gradient.addColorStop(0, `rgba(102, 58, 243, ${alpha * 0.8})`);
        gradient.addColorStop(0.5, `rgba(102, 58, 243, ${alpha * 0.3})`);
        gradient.addColorStop(1, `rgba(102, 58, 243, 0)`);

        this.ctx.fillStyle = gradient;
        this.ctx.beginPath();
        this.ctx.arc(x, y, size * 2, 0, Math.PI * 2);
        this.ctx.fill();

        // Center dot
        this.ctx.fillStyle = `rgba(211, 228, 250, ${alpha})`;
        this.ctx.beginPath();
        this.ctx.arc(x, y, size, 0, Math.PI * 2);
        this.ctx.fill();
    }

    animate() {
        this.drawBackground();
        this.drawGrid();
        requestAnimationFrame(() => this.animate());
    }
}

// Initialize on DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new InteractiveGridBackground();
    });
} else {
    new InteractiveGridBackground();
}
