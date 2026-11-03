/* A read-only display projection. Source audit events are never changed or sorted. */
(function (global, factory) {
    const timeline = factory();
    if (typeof module === 'object' && module.exports) module.exports = timeline;
    if (global) global.ServiceJobTimeline = timeline;
})(typeof window === 'undefined' ? null : window, function () {
    'use strict';
    const photoPrefixes = ['Fotografie: ', 'Fotografie doplněná po dokončení: ', 'Fotografie doplněna po dokončení: '];
    const statusTitles = {received: 'Přijato do servisu', in_progress: 'Probíhá oprava', completed: 'Servis dokončen', cancelled: 'Zakázka zrušena', handed_over: 'Vozidlo předáno zákazníkovi'};
    const timestampPattern = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})?$/;

    // Unzoned backend timestamps mean UTC, independent of the browser time zone.
    // Validate calendar values before Date can roll an invalid date into next month.
    function parsedTimestamp(raw) {
        if (typeof raw !== 'string') return null;
        const match = timestampPattern.exec(raw);
        if (!match || match[0] !== raw) return null;
        const [, y, mo, d, h, mi, s, fraction, zone] = match;
        const [year, month, day, hour, minute, second] = [y, mo, d, h, mi, s].map(Number);
        if (year < 1 || month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 59) return null;
        const date = new Date(0);
        date.setUTCFullYear(year, month - 1, day);
        date.setUTCHours(hour, minute, second, 0);
        if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
        let offset = 0;
        if (zone && zone !== 'Z') {
            const hours = Number(zone.slice(1, 3)), minutes = Number(zone.slice(4, 6));
            if (hours > 23 || minutes > 59) return null;
            offset = (zone[0] === '-' ? -1 : 1) * (hours * 3600 + minutes * 60);
        }
        // Keep seconds and the padded fraction separate: adding 1ns to a modern
        // epoch Number would round it away before the audit-order/window checks.
        return {seconds: date.getTime() / 1000 - offset, nanoseconds: Number((fraction || '').padEnd(9, '0'))};
    }
    function timestamp(raw) {
        const value = parsedTimestamp(raw);
        return value === null ? null : value.seconds + value.nanoseconds / 1e9;
    }
    const compareTimestamps = (left, right) => left.seconds - right.seconds || left.nanoseconds - right.nanoseconds;
    const withinPhotoWindow = (first, next) => {
        const seconds = next.seconds - first.seconds;
        return compareTimestamps(next, first) >= 0 && (seconds < 300 || seconds === 300 && next.nanoseconds <= first.nanoseconds);
    };
    const statusTitle = status => Object.prototype.hasOwnProperty.call(statusTitles, status) ? statusTitles[status] : 'Záznam zakázky';
    const isPhoto = event => typeof event.message === 'string' && photoPrefixes.some(prefix => event.message.startsWith(prefix));
    function rows(events) {
        if (!Array.isArray(events)) return [];
        const result = [];
        events.forEach((event, index) => {
            const photo = isPhoto(event), last = result[result.length - 1];
            const first = last && last.events[0];
            const start = first && parsedTimestamp(first.created_at), previous = last && parsedTimestamp(last.events[last.events.length - 1].created_at), current = parsedTimestamp(event.created_at);
            if (photo && last && last.kind === 'photo' && Number.isSafeInteger(event.actor_id) && event.actor_id > 0 && event.actor_id === first.actor_id && typeof event.status === 'string' && event.status.length > 0 && event.status === first.status && start !== null && previous !== null && current !== null && compareTimestamps(current, previous) >= 0 && withinPhotoWindow(start, current) && Math.floor(current.seconds / 86400) === Math.floor(start.seconds / 86400)) {
                last.events.push(event);
            } else {
                const sameStatus = typeof event.status === 'string' && event.status.length > 0 && index > 0 && events[index - 1].status === event.status;
                const title = typeof event.message === 'string' && event.message.startsWith('Dokument: ') ? 'Přidán dokument' : sameStatus ? 'Doplněna informace' : statusTitle(event.status);
                result.push({firstIndex: index, kind: photo ? 'photo' : 'event', title, events: [event]});
            }
        });
        return result;
    }
    function rowTitle(row) {
        if (row.kind === 'photo') return row.events.length === 1 ? 'Přidána fotografie · 1' : 'Přidány fotografie · ' + row.events.length;
        return row.title;
    }
    const css = `
.job-timeline {margin-block:1rem; min-width:0;}
.job-timeline > h4 {margin:0 0 .65rem; font-size:1rem;}
.job-timeline .job-timeline-list {list-style:none; margin:0; padding:0;}
.job-timeline .job-timeline-row {position:relative; margin:0; padding:0 0 .8rem 1.25rem; border-left:2px solid #c6d6d9; overflow-wrap:anywhere;}
.job-timeline .job-timeline-row:last-child {padding-bottom:0; border-left-color:transparent;}
.job-timeline .job-timeline-row::before {content:''; position:absolute; left:-5px; top:.35rem; width:8px; height:8px; border-radius:50%; background:#24757b;}
.job-timeline .job-timeline-header {display:flex; gap:.25rem .75rem; flex-wrap:wrap; align-items:baseline;}
.job-timeline .job-timeline-time {font-size:.8rem; color:#657277;}
.job-timeline .job-timeline-message {white-space:pre-wrap; margin:.2rem 0 0; font-size:.9rem;}
.job-timeline .job-timeline-toggle {display:inline-block; width:auto; max-width:100%; margin:.3rem 0 0; padding:.2rem .5rem; min-height:32px; font-size:.8rem;}
.job-timeline .job-timeline-originals {margin:.4rem 0 0; padding-left:1.1rem;}
.job-timeline .job-timeline-originals > li {margin:.3rem 0;}
.job-timeline [hidden] {display:none !important;}
`;
    let nextComponentId = 0;
    function render(document, events) {
        const componentId = ++nextComponentId, section = document.createElement('section');
        section.className = 'job-timeline';
        section.setAttribute('aria-label', 'Průběh zakázky');
        section.setAttribute('data-job-timeline', '');
        const style = document.createElement('style'); style.textContent = css;
        const title = document.createElement('h4'); title.textContent = 'Průběh zakázky';
        section.append(style, title);
        const projected = rows(events);
        if (!projected.length) {
            const empty = document.createElement('p'); empty.textContent = 'Historie zatím neobsahuje žádné události.'; section.append(empty); return section;
        }
        const list = document.createElement('ol'); list.className = 'job-timeline-list'; section.append(list);
        const timeNode = raw => {
            const time = document.createElement('time'), value = timestamp(raw);
            time.className = 'job-timeline-time';
            time.textContent = value === null ? String(raw || 'Čas neuveden') : new Date(value * 1000).toLocaleString('cs-CZ');
            if (value !== null) time.setAttribute('datetime', new Date(value * 1000).toISOString());
            return time;
        };
        const messageNode = message => {
            const text = document.createElement('p'); text.className = 'job-timeline-message'; text.textContent = typeof message === 'string' ? message : ''; return text;
        };
        projected.forEach(row => {
            const item = document.createElement('li'), header = document.createElement('div'), name = document.createElement('strong');
            item.className = 'job-timeline-row'; item.setAttribute('data-timeline-kind', row.kind); item.setAttribute('data-timeline-count', String(row.events.length)); item.setAttribute('data-timeline-first-index', String(row.firstIndex));
            header.className = 'job-timeline-header'; name.textContent = rowTitle(row);
            header.append(name, timeNode(row.events[row.events.length - 1].created_at)); item.append(header);
            if (row.kind === 'photo') {
                const button = document.createElement('button'), originals = document.createElement('ol');
                const disclosure = row.events.length > 1 ? 'jednotlivé fotografie (' + row.events.length + ')' : 'původní záznam';
                if (row.events.length === 1) {
                    const message = row.events[0].message, prefix = photoPrefixes.find(value => message.startsWith(value));
                    item.append(messageNode(message.slice(prefix.length)));
                }
                button.type = 'button'; button.className = 'job-timeline-toggle'; button.textContent = 'Zobrazit ' + disclosure;
                const id = 'job-timeline-' + componentId + '-events-' + row.firstIndex;
                button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', id);
                originals.id = id; originals.className = 'job-timeline-originals'; originals.hidden = true; originals.style.display = 'none';
                row.events.forEach(event => { const original = document.createElement('li'); original.append(timeNode(event.created_at), messageNode(event.message)); originals.append(original); });
                button.addEventListener('click', () => {
                    const expanded = button.getAttribute('aria-expanded') === 'true';
                    button.setAttribute('aria-expanded', String(!expanded)); originals.hidden = expanded; originals.style.display = expanded ? 'none' : 'block';
                    button.textContent = (expanded ? 'Zobrazit ' : 'Skrýt ') + disclosure;
                });
                item.append(button, originals);
            } else item.append(messageNode(row.events[0].message));
            list.append(item);
        });
        return section;
    }
    return Object.freeze({timestamp, rows, rowTitle, statusTitle, render});
});
