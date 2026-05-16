const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;

const html = fs.readFileSync('web/index.html', 'utf-8');
const dom = new JSDOM(html, { runScripts: "dangerously" });

let errors = [];
dom.window.onerror = function(msg, source, lineno, colno, error) {
    errors.push(`${msg} at line ${lineno}:${colno}`);
};

setTimeout(() => {
    if (errors.length > 0) {
        console.log("Errors found:");
        console.log(errors.join('\n'));
    } else {
        console.log("No syntax errors found on load.");
    }
}, 1000);
