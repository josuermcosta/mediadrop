var scripts = document.getElementById('arguments');
var show = scripts.getAttribute('show');
var audio = scripts.getAttribute('audio');
show = show.replace(/'/g, '"');
audio = audio.replace(/'/g, '"');
video = podlovePlayer('#podlovePlayer', {show: JSON.parse(show), audio: JSON.parse(audio)});