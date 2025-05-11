document.addEventListener('DOMContentLoaded', function() {

    
    const fileInput = document.getElementById('fileInput');
    const packetList = document.getElementById('packetList');
    const packetPreview = document.getElementById('packetPreview');
    const progressBar = document.getElementById('progressBar');
    const progressDiv = document.querySelector('.progress');

    fileInput.addEventListener('change', function() {
        const file = fileInput.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = function(e) {
            const data = e.target.result;
            const packetSize = 1024; // 1 KB per packet
            packetList.innerHTML = '';
            packetPreview.style.display = 'block';

            for (let i = 0; i < data.length; i += packetSize) {
                const packet = data.slice(i, i + packetSize);
                const item = document.createElement('li');
                item.className = 'list-group-item';
                item.textContent = `Packet ${i / packetSize + 1}: ${btoa(packet).substring(0, 50)}...`;
                packetList.appendChild(item);
            }
        };
        reader.readAsBinaryString(file);
    });

    const uploadForm = document.getElementById('uploadForm');
    uploadForm.addEventListener('submit', function(e) {
        progressDiv.style.display = 'block';
        const fakeUpload = setInterval(() => {
            let current = parseInt(progressBar.style.width) || 0;
            if (current >= 100) {
                clearInterval(fakeUpload);
            } else {
                current += 10;
                progressBar.style.width = current + '%';
                progressBar.textContent = current + '%';
            }
        }, 100);
    });
});
