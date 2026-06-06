import os

html_path = "/Users/nandan/Documents/Personal/Projects/DeliriumWatch/flaskui/templates/index.html"
with open(html_path, "r") as f:
    text = f.read()

# 1. Adjust sizing to fit Lorazepam
text = text.replace('class="col-4"><label class="form-label">Propofol', 'class="col-3"><label class="form-label">Propofol')
text = text.replace('class="col-4"><label class="form-label">Fentanyl', 'class="col-3"><label class="form-label">Fentanyl')
text = text.replace('class="col-4"><label class="form-label">Midaz', 'class="col-3"><label class="form-label">Midaz')

# 2. Insert Lorazepam Option
lorazepam_html = '\n                        <div class="col-3"><label class="form-label">Lorazepam (mg)</label><input type="number" step="0.1" class="form-control form-control-sm" name="lorazepam_total" value="{{ values[\'lorazepam_total\'] }}"></div>\n                      </div>'
text = text.replace('value="{{ values[\'midazolam_total\'] }}"></div>\n                      </div>', 'value="{{ values[\'midazolam_total\'] }}"></div>' + lorazepam_html)

# 3. Add Live Patient Telemetry Board (ECG/EEG Canvas)
telemetry_html = '''
            <!-- LIVE TELEMETRY -->
            <div class="row gx-3 mb-3 no-print">
                <div class="col-12">
                    <div class="card-emr shadow-sm bg-dark" style="border: 2px solid #333;">
                        <div class="card-header-emr bg-black text-info border-dark d-flex justify-content-between align-items-center">
                            <span><i class="fa-solid fa-satellite-dish me-2"></i> Real-time Patient Telemetry (EEG / ECG Vector)</span>
                            <span class="badge border border-success text-success bg-transparent live-indicator"><i class="fa-solid fa-wifi me-1"></i> MONITORING</span>
                        </div>
                        <div class="card-body p-1" style="background-color: #0b0f19;">
                            <canvas id="telemetryCanvas" style="width: 100%; height: 130px; display: block;"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Result Banner Row -->
'''
text = text.replace('<!-- Result Banner Row -->', telemetry_html)

# 4. Add the Animation Engine to the Javascript
canvas_js = '''
      // TELEMETRY ANIMATION (EEG/ECG Mock)
      const telCanvas = document.getElementById('telemetryCanvas');
      if(telCanvas) {
          const tCtx = telCanvas.getContext('2d');
          telCanvas.width = telCanvas.offsetWidth * 2; // Hi-DPI
          telCanvas.height = telCanvas.offsetHeight * 2;
          tCtx.scale(2, 2);
          const w = telCanvas.offsetWidth;
          const h = telCanvas.offsetHeight;
          let offsetPoints = 0;
          let ecgPoints = Array(w).fill(0);
          let eegPoints = Array(w).fill(0);
          
          function drawTelemetry() {
              tCtx.fillStyle = 'rgba(11, 15, 25, 0.3)'; // Fade effect
              tCtx.fillRect(0, 0, w, h);
              offsetPoints += 3;
              
              // ECG Generation
              ecgPoints.shift();
              if (Math.random() < 0.015) { // Heartbeat
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
              for(let i=0; i<ecgPoints.length; i++) tCtx.lineTo(i, h/3 - ecgPoints[i]);
              tCtx.stroke();
              
              // Render EEG (Cyan)
              tCtx.strokeStyle = '#00e5ff';
              tCtx.lineWidth = 1.5;
              tCtx.beginPath();
              for(let i=0; i<eegPoints.length; i++) tCtx.lineTo(i, (h/3)*2 - eegPoints[i]);
              tCtx.stroke();
              
              requestAnimationFrame(drawTelemetry);
          }
          drawTelemetry();
      }

      renderCharts();
'''
if 'telemetryCanvas' not in text:
    text = text.replace('renderCharts();\n    </script>', canvas_js + '\n    </script>')

with open(html_path, "w") as f:
    f.write(text)

print("Project Updated! Reload your browser.")
