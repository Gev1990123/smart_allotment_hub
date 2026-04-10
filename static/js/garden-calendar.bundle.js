import React from 'react';
import { createRoot } from 'react-dom/client';
import GardeningCalendar from './gardening_calendar';

const root = createRoot(document.getElementById('garden-calendar-root'));
root.render(<GardeningCalendar />);