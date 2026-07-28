import { useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, ListTodo } from "lucide-react";

export type CalendarLearningItem = {
  id: string;
  title: string;
  date: Date;
  tone: "active" | "overdue" | "complete";
};

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const locale = document.documentElement.lang || "en";
const monthFormatter = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" });
const dayFormatter = new Intl.DateTimeFormat(locale, { weekday: "long", month: "long", day: "numeric", year: "numeric" });

function sameDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

function calendarDays(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(month.getFullYear(), month.getMonth(), 1 - first.getDay());
  return Array.from({ length: 42 }, (_, index) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + index));
}

export function LearningCalendar({ items, initialDate = new Date(), selectedItemId = null, onSelectItem, onClose }: {
  items: CalendarLearningItem[];
  initialDate?: Date;
  selectedItemId?: string | null;
  onSelectItem?: (item: CalendarLearningItem) => void;
  onClose?: () => void;
}) {
  const [month, setMonth] = useState(() => new Date(initialDate.getFullYear(), initialDate.getMonth(), 1));
  const today = initialDate;
  const days = useMemo(() => calendarDays(month), [month]);
  const moveMonth = (offset: number) => setMonth((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1));

  return (
    <section className="learning-calendar" aria-label="Learning task calendar">
      <header className="learning-calendar-toolbar">
        <div className="calendar-legend" aria-label="Calendar task types">
          {onClose ? <button type="button" onClick={onClose}><ListTodo size={14} aria-hidden="true" />Back to tasks</button> : <span className="active">Tasks</span>}
        </div>
        <div className="calendar-month-control">
          <button type="button" aria-label="Previous month" onClick={() => moveMonth(-1)}><ChevronLeft size={16} /></button>
          <h2 aria-live="polite">{monthFormatter.format(month)}</h2>
          <button type="button" aria-label="Next month" onClick={() => moveMonth(1)}><ChevronRight size={16} /></button>
        </div>
        <div className="calendar-view-control"><span>Month</span><CalendarDays size={15} aria-hidden /></div>
      </header>
      <div className="calendar-weekdays" aria-hidden>{weekdays.map((day) => <span key={day}>{day}</span>)}</div>
      <div className="calendar-grid" role="grid" aria-label={monthFormatter.format(month)}>
        {days.map((day) => {
          const dayItems = items.filter((item) => sameDay(item.date, day));
          const outside = day.getMonth() !== month.getMonth();
          const current = sameDay(day, today);
          return (
            <div className={`calendar-day ${outside ? "outside" : ""} ${current ? "today" : ""}`} role="gridcell" aria-label={dayFormatter.format(day)} key={day.toISOString()}>
              <time dateTime={`${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`}>{day.getDate()}</time>
              <div className="calendar-events">{dayItems.slice(0, 2).map((item) => <button
                type="button"
                className={`calendar-event ${item.tone} ${selectedItemId === item.id ? "selected" : ""}`}
                title={item.title}
                aria-label={`Show task: ${item.title}`}
                aria-pressed={selectedItemId === item.id}
                aria-controls={`feed-task-${item.id}`}
                onClick={() => onSelectItem?.(item)}
                key={item.id}
              >{item.title}</button>)}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
