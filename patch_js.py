html_path = "flaskui/templates/index.html"
with open(html_path, "r") as f:
    text = f.read()

canvas_js = '''
      // TELEMETRY ANIMATION (EEG/ECG Mock)
      const telCanvas = document.getElementById('telemetryCanvas');
      if(telCanvas) {
          const tCtx = telCanvas.getContext('2d');
          
          // Use hardcoded fallback if offsetWidth isn't immediate
          const targetW = telCanvas.offsetWidth || 800;
          const targetH = telCanvas.offsetHeight || 130;
          
          telCanvas.width = targetW * 2; // Hi-DPI
          telCanvas.height = targetH * 2;
          tCtx.scale(2, 2);
          const w = targetW;
          const h = targetH;
          let offsetPoints = 0;
          let ecgPoints = [];
          for(let i=0; i<w; i++) ecgPoints.push(0);
          let eegPoints = [];
          for(let i=0; i<w; i++) eegPoints.push(0);
          
          function drawTelemetry() {
              tCtx.fillStyle = 'rgba(11, 15, 25, 0.3)'; // Fade effect
              tCtx.fillRect(0, 0, w, h);
              offsetPoints += 3;
              
              // ECG Generation
              ecgPoints.shift();
              if (Math.random() < 0.012) { // Heartbeat
                  ecgPoints.push(-30, 45, -15); 
              } else {
                  ecgPoints.push((Math.random() - 0.5) * 3); // Baseline noise
              }
              
              // EEG Wave Generation (Sine waves + noise for brain activity)
              eegPoints.shift();
              eegPoints.push( Math.sin(offsetPoints/12)*8 + Math.cos(offsetPoints/20)*6 + (Math.random()-0.5)*5 );
              
              // Draw Grid System
              tCtx.strokeStyle = 'rgba(0, 255, 100, 0.05)';
              tCtx.lineWidth = 1;
              tCtx.beginPath();
              for(let i=(offsetPoints*2)%40; i<w; i+=40) {
                  tCtx.moveTo(i, 0); tCtx.lineTo(i, h);
              }
              tCtx.stroke();
              
              // Render ECG (Neon Green)
              tCtx.strokeStyle = '#00ff66';
              tCtx.lineWidth = 2;
              tCtx.beginPath();
              for(let i=0; i<ecgPoints.length; i++) tCtx.lineTo(i, h/3 - (ecgPoints[i] || 0));
              tCtx.stroke();
              
              // Render EEG (Cyan)
              tCtx.strokeStyle = '#00e5ff';
              tCtx.lineWidth = 1.5;
              tCtx.beginPath();
              for(let i=0; i<eegPoints.length; i++) tCtx.lineTo(i, (h/3)*2 - (eegPoints[i] || 0));
              tCtx.stroke();
              
              requestAnimationFrame(drawTelemetry);
          }
          drawTelemetry();
      }
'''

if 'TELEMETRY ANIMATION' not in text:
    text = text.replace('renderCharts();\n    </script>', canvas_js + '\n      renderCharts();\n    </script>')
    # Fallback if that exact string isn't there
    if 'TELEMETRY ANIMATION' not in text:
        text = text.replace('renderCharts();', canvas_js + '\n      renderCharts();')

with open(html_path, "w") as f:
    f.write(text)

print("done")
